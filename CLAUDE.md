# CLAUDE.md — Media GPT Image 2

## 项目概述

Chrome 插件（browser extension）+ local_bridge（HTTP server）的自动化生图系统。插件在网页上自动执行操作（点击、上传、填写），bridge 负责任务队列和 Media AI API 交互。

## 系统架构

```
┌─────────────────────────┐         ┌──────────────────────────┐
│   Chrome Extension       │         │     local_bridge         │
│   (content-script.js)   │         │     (server.py)          │
│                         │         │                          │
│  · 轮询 /v1/job/claim   │◄───────►│  · 任务队列 JobStore     │
│  · 读取 job.platform    │  HTTP   │  · POST /v1/jobs         │
│  · 读取 job.targetUrl   │         │  · GET /v1/state         │
│  · 调用平台 handler     │         │  · Media AI API 客户端   │
│    - runGptJob          │         │                          │
│    - runJimengImageJob  │         │                          │
│    - runJimengVideoJob  │         │                          │
└─────────────────────────┘         └──────────────────────────┘
            │                                    │
            │                                    ▼
            │                         ┌──────────────────┐
            │                         │  Media AI API    │
            │                         │  (localhost:3000)│
            └────────────────────────►└──────────────────┘
```

### 两个任务提交流程

**流程 A（正确路径）：插件直接调用 single endpoint**
```
插件 → POST /v1/single/jimeng-image {styleImageId, sceneId}
     → server 内部构建 Job，platform/targetUrl 直接写死
     → 插件 claim 时 to_public_dict() 有 platform="jimeng"
```

**流程 B（submit 脚本路径）：通过 caseFiles 提交**
```
submit_xxx.py → POST /v1/jobs {caseFiles: [path, ...]}
             → server.build_jobs(case_paths) 读取 .media-ai.json sidecar
             → 根据 kind 映射 platform/targetUrl
             → 插件 claim 时 to_public_dict() 有 platform
```

### 插件如何知道打开哪个网站

插件轮询 `GET /v1/job/claim`，拿到 job 后读取：
- `job.platform` → 决定用哪个 handler
- `job.targetUrl` → 决定打开哪个 URL

```
platform="gpt"         → runGptJob (ChatGPT)
platform="jimeng"      → runJimengImageJob / runJimengVideoJob (jimeng.jianying.com，图片/视频模式由 targetUrl 区分)
```

## 核心数据结构

### Job 数据类（server.py）
```python
@dataclass
class Job:
    id: str                           # 任务 ID
    case_file: pathlib.Path           # task.md 路径
    prompt: str                       # 提示词
    assets: list[dict]                # 图片资产 [{label, name, mimeType, sha256}]
    output_dir: pathlib.Path          # 输出目录
    status: str = "pending"           # pending/claimed/completed/failed
    media_ai: dict | None = None     # .media-ai.json sidecar 内容
    platform: str | None = None       # gpt / jimeng
    target_url: str | None = None     # https://jimeng.jianying.com/...
```

### .media-ai.json sidecar（任务元数据）
**文件名必须是 `task.media-ai.json`**，与 `task.md` 同目录。

| 字段 | 说明 |
|------|------|
| `kind` | 任务类型，决定 platform 映射 |
| `baseUrl` | Media AI 服务地址 |
| `productId` | 产品 ID |
| `ipId` | IP ID |
| `styleImageId` | 定妆图 ID（首帧图用） |
| `sceneId` | 场景 ID |
| `modelImageId` | 模特图 ID（定妆图用） |
| `poseId` | 姿势 ID |
| `uploadSubDir` | 上传子目录 |

**kind → platform 映射（build_jobs 中定义）：**
```
jimeng-image       → platform="jimeng", targetUrl="...?type=image"
jimeng-video (kind="video") → platform="jimeng", targetUrl="...?type=video"
first-frame-image  → platform="gpt"
style-image        → platform="gpt"
model-image        → platform="gpt"
(其他)              → platform=None, targetUrl=None
```

### platform handler（extension/content-handlers/）
- `gpt.js` → `runGptJob` → ChatGPT
- `jimeng-image.js` → `runJimengImageJob` → jimeng.jianying.com（图片）
- `jimeng-video.js` → `runJimengVideoJob` → jimeng.jianying.com（视频）

## 核心 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/v1/state` | 任务队列状态（job 列表） |
| GET | `/v1/job/claim` | 插件获取下一个任务 |
| POST | `/v1/jobs` | 批量提交任务（body: `{caseFiles: [path,...]}`） |
| POST | `/v1/single/{type}` | 单任务端点（插件直接调用的正确路径） |
| POST | `/v1/job/{id}/progress` | 插件上报进度 |
| POST | `/v1/job/{id}/complete` | 插件标记完成 |

## 任务生命周期

```
pending → claimed → completed
                   └──→ failed
```

1. submit 脚本或插件提交任务（pending）
2. 插件轮询 `/v1/job/claim` 认领任务（claimed）
3. 插件执行浏览器自动化
4. 插件调用 `/v1/job/{id}/complete` 或 `/v1/job/{id}/fail`

## 认证

**不要手动管理 cookie**。通过 `read_cookie()`（`local_bridge/utils.py`）自动处理：

1. 显式传入的 `--cookie` / `--cookie-file` 参数
2. `MEDIA_AI_COOKIE` 环境变量
3. **持久缓存** `~/.cache/media-ai-cookie.json`（首次登录后自动保存，下次脚本执行直接复用）
4. `.env` 文件中的 `MEDIA_AI_USER` / `MEDIA_AI_PASSWORD`，自动登录后写入缓存

**缓存机制**：
- 缓存在 `~/.cache/media-ai-cookie.json`（跨脚本进程复用）
- 每次使用前通过 `/api/products?limit=1` 验证 cookie 有效性
- 收到 401/403 自动清除缓存，重新登录并更新缓存
- 显式传入的 cookie（`--cookie`、`--cookie-file`、环境变量）不经过缓存校验

## 任务提交文档

### Submit 脚本 → API 端点 → Platform 映射总表

| Submit 脚本 | API 端点 | HTTP | Task kind | Platform | 说明 |
|------------|---------|------|-----------|----------|------|
| `scripts/submit_jimeng_image.py` | `/v1/single/jimeng-image` | POST | `jimeng-image` | `jimeng` | 即梦文生图（插件直接调 single endpoint） |
| `scripts/submit_jimeng_video.py` | `/v1/single/jimeng-video` | POST | `video` | `jimeng` | 即梦文生视频（插件直接调 single endpoint） |
| `scripts/submit_media_ai_first_frame_images.py` | `/v1/jobs` | POST | `first-frame-image` | `gpt` | 批量提交首帧图任务 |
| `scripts/submit_media_ai_style_images.py` | `/v1/jobs` | POST | `style-image` | `gpt` | 批量提交定妆图任务 |
| `scripts/submit_media_ai_model_images.py` | `/v1/jobs` | POST | `model-image` | `gpt` | 批量提交模特图任务 |

### Platform 说明

- **`gpt`**：GPT 生图任务，插件轮询 `/v1/job/claim` 认领后执行浏览器自动化（ChatGPT）
- **`jimeng`**：即梦任务，即梦插件自动化（jimeng.jianying.com），图片/视频模式由 `targetUrl` 区分

### 使用示例

#### 直接 HTTP API（curl）

**POST /v1/jobs** — 批量提交任务文件：
```bash
curl -X POST http://localhost:8765/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{"caseFiles": ["runs/xxx/task.md"]}'
```

**POST /v1/single/jimeng-image** — 即梦文生图：
```bash
curl -X POST http://localhost:8765/v1/single/jimeng-image \
  -H "Content-Type: application/json" \
  -d '{"styleImageId": "<id>", "sceneId": "<id>"}'
```

**POST /v1/single/jimeng-video** — 即梦文生视频：
```bash
curl -X POST http://localhost:8765/v1/single/jimeng-video \
  -H "Content-Type: application/json" \
  -d '{"productId": "<id>", "firstFrameId": "<id>"}'
```

**POST /v1/single/first-frame-image** — 首帧图（GPT）：
```bash
curl -X POST http://localhost:8765/v1/single/first-frame-image \
  -H "Content-Type: application/json" \
  -d '{"styleImageId": "<id>", "sceneId": "<id>"}'
```

**POST /v1/single/style-image** — 定妆图（GPT）：
```bash
curl -X POST http://localhost:8765/v1/single/style-image \
  -H "Content-Type: application/json" \
  -d '{"modelImageId": "<id>", "poseId": "<id>"}'
```

**POST /v1/single/model-image** — 模特图（GPT）：
```bash
curl -X POST http://localhost:8765/v1/single/model-image \
  -H "Content-Type: application/json" \
  -d '{"productId": "<id>", "ipId": "<id>"}'
```

#### Submit 脚本（推荐）

```bash
# 即梦生图
PYTHONPATH=. uv run python scripts/submit_jimeng_image.py \
  --style-image-id <id> --scene-id <id>

# 即梦视频
PYTHONPATH=. uv run python scripts/submit_jimeng_video.py \
  --first-frame-id <id> --pose-id <id>

# GPT 首帧图
PYTHONPATH=. uv run python scripts/submit_media_ai_first_frame_images.py \
  --style-image-id <id> --scene-id <id> --dry-run

# GPT 定妆图
PYTHONPATH=. uv run python scripts/submit_media_ai_style_images.py \
  --model-image-id <id> --pose-id <id> --dry-run

# GPT 模特图
PYTHONPATH=. uv run python scripts/submit_media_ai_model_images.py \
  --product-id <id> --dry-run
```

> **路由逻辑**：API `/v1/jobs` 收到 caseFiles 后，`build_jobs()` 读取 `task.media-ai.json` 的 `kind` 字段决定 platform——`jimeng-image` → `jimeng`，`video`（即 jimeng-video） → `jimeng`，`first-frame-image/style-image/model-image` → `gpt`。插件 claim 到 job 后读取 `job.platform` 选择对应 handler 执行。

## 核心文件

| 文件 | 职责 |
|------|------|
| `extension/content-script.js` | 插件主体，轮询 job，执行平台 handler |
| `extension/content-handlers/jimeng-image.js` | 即梦图片浏览器自动化（S1-S9） |
| `extension/content-handlers/jimeng-video.js` | 即梦视频浏览器自动化 |
| `extension/popup.js` | 插件 popup UI |
| `local_bridge/server.py` | Bridge HTTP 服务器，任务队列，API 端点 |
| `local_bridge/media_ai_client.py` | Media AI API 客户端（认证内置） |
| `local_bridge/utils.py` | 共享工具函数（所有 submit 脚本统一调用） |
| `local_bridge/single_task.py` | 任务构建器（向后兼容导出） |
| `scripts/submit_*.py` | 任务提交脚本 |

## 调试

- bridge 健康检查：`curl http://localhost:8765/health`
- 查看 bridge 日志：`tail -f runs/bridge.log`
- 跑单元测试：`PYTHONPATH=. uv run pytest tests/ -v`
- 插件测试：在 popup UI 中点击 S1-S9 按钮逐步验证

## 注意事项

### sidecar 文件名（重要）
- **必须**是 `task.media-ai.json`，不是 `.media-ai.json`
- `load_media_ai_sidecar()` 函数读取 `task.with_suffix(".media-ai.json")`
- `media_ai_client.py` 写入用 `case_path.with_suffix(".media-ai.json")`
- 两者必须匹配

### kind 命名规范
- 使用 **kebab-case**：`jimeng-image`、`video`、`first-frame-image`、`style-image`、`model-image`
- `jimeng-video` 的 kind 值为 `video`（不是 `jimeng-video`）
- 不要用下划线：`jimeng_image`（已废弃，统一用 `jimeng`）

### 不要做的事
- **不要**用 curl 直接 POST bridge 端点（bridge 会做认证检查）
- **不要**手动管理 cookie 或告诉用户需要提供 cookie
- **不要**在 submit 脚本中相互导入（用 `from local_bridge.utils import`）
