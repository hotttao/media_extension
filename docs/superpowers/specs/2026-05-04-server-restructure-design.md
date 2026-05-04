# local_bridge 重构设计文档

## 概述

将 `server.py` 从手写 `BaseHTTPRequestHandler` 重构为 FastAPI + 轻量 DDD 架构，实现输入输出严格校验和自动 OpenAPI 文档生成。

**重构目标：**
- 输入校验：所有 HTTP 请求参数、body、路径变量全部通过 Pydantic 模型强校验
- 输出校验：所有 HTTP 响应通过 Pydantic Response 模型序列化
- 文档：FastAPI 自动生成 OpenAPI 3.0，Swagger UI 访问 `/docs`，ReDoc 访问 `/redoc`
- Postman Collection：从 `openapi.json` 一键生成

**不改变的内容：**
- 业务逻辑（JobStore、build_jobs、文件处理逻辑）原样迁移
- 现有 API 端点路径和语义保持不变（`/v1/jobs`、`/v1/job/claim` 等）
- Media AI 客户端（`media_ai_client.py`）保持独立模块

---

## 目标架构

```
local_bridge/
├── __init__.py
├── main.py                      # FastAPI app 实例、启动、shutdown
├── domain/
│   ├── __init__.py
│   ├── models.py                # Job dataclass、MediaAI sidecar（从 server.py 迁移）
│   └── services.py              # 业务逻辑：JobService（从 server.py 迁移）
├── api/
│   ├── __init__.py
│   ├── schemas.py                # 所有 Pydantic Request/Response 模型
│   └── routers/
│       ├── __init__.py
│       ├── jobs.py               # POST /v1/jobs, GET /v1/state
│       ├── job_claim.py          # GET /v1/job/claim
│       ├── job_progress.py       # POST /v1/job/{id}/progress
│       ├── job_result.py         # POST /v1/job/{id}/result
│       ├── job_fail.py           # POST /v1/job/{id}/fail
│       ├── job_requeue.py        # POST /v1/job/{id}/requeue
│       ├── job_cancel.py         # POST /v1/job/{id}/cancel
│       ├── jobs_cancel.py        # POST /v1/jobs/cancel
│       ├── single_model_image.py  # POST /v1/single/model-image
│       ├── single_style_image.py # POST /v1/single/style-image
│       ├── single_first_frame.py # POST /v1/single/first-frame-image
│       └── single_jimeng.py     # POST /v1/single/jimeng-image, /v1/single/jimeng-video
├── infrastructure/
│   ├── __init__.py
│   ├── persistence.py           # JobStore 实现（文件 I/O）
│   └── media_ai_client.py       # MediaAIClient（从上层迁移）
├── utils.py                     # 保持不变（ensure_text、slugify 等工具）
└── cli/
    └── commands.py               # CLI 入口（serve、inspect 命令）
```

---

## 核心模型定义

### Request Schemas（Pydantic）

```python
# /v1/jobs — 批量提交任务
class JobsCreateRequest(BaseModel):
    caseFiles: list[str]  # 路径列表

# /v1/single/jimeng-image — 即梦生图
class JimengImageCreateRequest(BaseModel):
    styleImageId: str
    sceneId: str | None = None
    productId: str | None = None
    ipId: str | None = None
    force: bool = False
    prompt: str | None = None
    noEmbedCookie: bool = False

# /v1/single/model-image
class ModelImageCreateRequest(BaseModel):
    modelImageId: str | None = None
    productId: str | None = None
    ipId: str | None = None
    force: bool = False

# /v1/single/style-image
class StyleImageCreateRequest(BaseModel):
    modelImageId: str
    poseId: str
    force: bool = False

# /v1/single/first-frame-image
class FirstFrameImageCreateRequest(BaseModel):
    styleImageId: str
    sceneId: str
    force: bool = False

# /v1/job/{id}/progress
class ProgressUpdateRequest(BaseModel):
    message: str
    at: str | None = None
    details: Any | None = None

# /v1/job/{id}/result
class ResultSubmitRequest(BaseModel):
    images: list[ImageResult]
    videos: list[VideoResult] = []
    assistantResponse: str | None = None
    logs: list | None = None

# /v1/job/{id}/fail
class FailSubmitRequest(BaseModel):
    reason: str
    logs: list | None = None
```

### Response Schemas（Pydantic）

```python
# 统一成功响应
class SuccessResponse(BaseModel):
    ok: bool = True

# 任务查询响应
class JobResponse(BaseModel):
    id: str
    caseFile: str
    prompt: str
    assets: list[AssetResponse]
    timeoutSeconds: int = 900
    platform: str | None = None
    targetUrl: str | None = None

# 任务状态列表
class StateResponse(BaseModel):
    jobs: list[JobStatusResponse]

# 单任务创建响应
class SingleJobCreatedResponse(BaseModel):
    ok: bool
    job: JobInfo | None = None
    dryRun: bool | None = None
    caseFile: str | None = None
    message: str | None = None
```

---

## API 路由映射

| 原路径 | 新 Router | 方法 | 说明 |
|--------|----------|------|------|
| `GET /health` | 内置 | GET | 健康检查（FastAPI 自动） |
| `GET /v1/state` | `jobs.py` | GET | 返回队列状态 |
| `POST /v1/jobs` | `jobs.py` | POST | 批量提交 |
| `GET /v1/job/claim` | `job_claim.py` | GET | 认领任务 |
| `POST /v1/job/{id}/progress` | `job_progress.py` | POST | 上报进度 |
| `POST /v1/job/{id}/result` | `job_result.py` | POST | 提交结果 |
| `POST /v1/job/{id}/fail` | `job_fail.py` | POST | 标记失败 |
| `POST /v1/job/{id}/requeue` | `job_requeue.py` | POST | 重队 |
| `POST /v1/job/{id}/cancel` | `job_cancel.py` | POST | 取消单个 |
| `POST /v1/jobs/cancel` | `jobs_cancel.py` | POST | 批量取消 |
| `POST /v1/single/model-image` | `single_model_image.py` | POST | 单任务：模特图 |
| `POST /v1/single/style-image` | `single_style_image.py` | POST | 单任务：定妆图 |
| `POST /v1/single/first-frame-image` | `single_first_frame.py` | POST | 单任务：首帧图 |
| `POST /v1/single/jimeng-image` | `single_jimeng.py` | POST | 单任务：即梦生图 |
| `POST /v1/single/jimeng-video` | `single_jimeng.py` | POST | 单任务：即梦视频 |

---

## OpenAPI 和 Postman 文档

### OpenAPI
- 访问 `GET /docs` → Swagger UI
- 访问 `GET /redoc` → ReDoc
- 访问 `GET /openapi.json` → 原始 OpenAPI JSON

### Postman Collection 生成
```bash
# 方式 1: openapi2postman（安装后）
openapi2postman -s http://localhost:8765/openapi.json -o bridge.json

# 方式 2: 直接在启动时导出
uvicorn main:app --factory --export-openapi bridge-openapi.json
```

---

## 迁移策略

**Phase 1：基础设施**
1. 创建目录结构
2. 迁移 `domain/models.py`（Job dataclass）
3. 迁移 `domain/services.py`（业务逻辑函数）
4. 迁移 `infrastructure/persistence.py`（JobStore）
5. 迁移 `infrastructure/media_ai_client.py`（保持原样复制）

**Phase 2：API 层**
1. 定义所有 Pydantic schemas
2. 实现各 router
3. 配置 FastAPI app，组装所有 router

**Phase 3：文档和 CLI**
1. 配置 OpenAPI metadata（title、version、description）
2. CLI 命令迁移到 `cli/commands.py`
3. 测试 Postman Collection 生成

---

## 错误处理

- 所有路由的 HTTP 异常通过 `HTTPException` 抛出
- 业务逻辑异常（JobStore、MediaAI）统一在 router 层捕获，转为 `500` 或具体 4xx
- 响应体格式统一为 `{ok: false, error: string, detail?: string}`

---

## 依赖变更

新增依赖：
- `fastapi>=0.115.0`
- `uvicorn[standard]>=0.30.0`
- `pydantic>=2.0`
- `openapi2postman`（仅文档生成，可选）

原有依赖不变（`media_ai_client.py` 依赖的 `requests`/`urllib` 保持）。

---

## 验证步骤

1. `uv run python -c "from local_bridge.main import app; print('OK')"` — 导入无报错
2. `curl http://localhost:8765/docs` — Swagger UI 可访问
3. `curl http://localhost:8765/openapi.json | jq '.info'` — OpenAPI JSON 有效
4. `openapi2postman -s http://localhost:8765/openapi.json -o /tmp/bridge.json` — Postman Collection 生成成功
5. 现有 submit 脚本功能回归：submit → claim → progress → complete 流程端到端通
