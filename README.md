# Media AI Bridge

Chrome 插件（browser extension）+ local_bridge（FastAPI 服务）的自动化生图系统。插件在网页上自动执行操作（点击、上传、填写），bridge 负责任务队列和 Media AI API 交互。

## 系统架构

```
┌───────────────────┐       ┌──────────────────────┐       ┌──────────────┐
│  Chrome Extension │◄─────►│   local_bridge       │─────►│ Media AI API │
│  content-script   │ HTTP  │   (FastAPI)          │       │ localhost:3000│
└───────────────────┘       └──────────────────────┘       └──────────────┘
                                    │
                                    ▼
                            ┌──────────────┐
                            │ Job Manager  │
                            │ /manage/     │
                            └──────────────┘
```

## 快速开始

### 启动服务

```bash
# 使用 uv（推荐）
uv run python -m local_bridge serve

# 或直接
python -m local_bridge serve --host 127.0.0.1 --port 8765
```

服务地址：`http://127.0.0.1:8765`
Job Manager UI：`http://localhost:8765/manage/`

### 提交任务

```bash
# 即梦图片任务
PYTHONPATH=. uv run python -m scripts.submit_jimeng_image \
  --style-image-id <id> --scene-id <id> --no-wait

# 模特图任务
PYTHONPATH=. uv run python -m scripts.submit_media_ai_model_images \
  --product-id <id> --ip-id <id> --no-wait

# 即梦视频任务
PYTHONPATH=. uv run python -m scripts.submit_jimeng_video \
  --first-frame-id <id> --pose-id <id> --no-wait
```

## 目录结构

```
local_bridge/
├── main.py                    # FastAPI 应用入口
├── api/
│   ├── routers/               # API 路由（DDD 风格）
│   │   ├── jobs.py            # /v1/jobs
│   │   ├── job_single.py      # /v1/job/{id}/*
│   │   └── job_progress.py     # /v1/job/claim
│   └── schemas.py             # Pydantic 请求/响应模型
├── domain/
│   └── models.py              # Job 数据模型
├── infrastructure/
│   ├── persistence.py         # JobStore 持久化
│   └── media_ai_client.py     # Media AI API 客户端
├── utils.py                   # 共享工具（cookie/bridge/等）
└── single_task.py             # 单任务端点构造器

extension/                     # Chrome 扩展
├── content-script.js          # 主体，轮询 /v1/job/claim
└── content-handlers/          # 平台 handler
    ├── jimeng-image.js
    ├── jimeng-video.js
    └── gpt.js

scripts/
├── submit_jimeng_image.py     # 即梦图片提交
├── submit_jimeng_video.py     # 即梦视频提交
├── submit_media_ai_model_images.py   # 模特图提交
├── submit_media_ai_style_images.py  # 定妆图提交
├── submit_media_ai_first_frame_images.py  # 首帧图提交
└── generate_docs.py           # 生成 OpenAPI/Postman 文档

docs/
├── openapi.json               # OpenAPI 3.1 规范
├── openapi.yaml               # YAML 格式
└── media-ai-bridge.postman_collection.json  # Postman 集合
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/state` | 任务队列状态 |
| POST | `/v1/jobs` | 批量提交任务（caseFiles 数组） |
| GET | `/v1/job/claim` | 插件认领任务 |
| POST | `/v1/job/{job_id}/progress` | 上报进度 |
| POST | `/v1/job/{job_id}/result` | 提交结果 |
| POST | `/v1/job/{job_id}/fail` | 标记失败 |
| POST | `/v1/job/{job_id}/requeue` | 重新排队 |
| POST | `/v1/job/{job_id}/cancel` | 取消任务 |
| DELETE | `/v1/job/{job_id}` | 删除任务 |
| POST | `/v1/jobs/cancel` | 取消所有 pending 任务 |
| POST | `/v1/single/model-image` | 创建模特图任务 |
| POST | `/v1/single/style-image` | 创建定妆图任务 |
| POST | `/v1/single/first-frame-image` | 创建首帧图任务 |
| POST | `/v1/single/jimeng-image` | 创建即梦图片任务 |
| POST | `/v1/single/jimeng-video` | 创建即梦视频任务 |

完整文档见 `docs/openapi.json`（可用 Postman 导入 `docs/media-ai-bridge.postman_collection.json`）。

## 认证

**不要手动管理 cookie**。通过 `read_cookie()` 自动处理：

1. 显式 `--cookie` / `--cookie-file` 参数
2. `MEDIA_AI_COOKIE` 环境变量
3. **持久缓存** `~/.cache/media-ai-cookie.json`（首次登录后自动保存，下次复用）
4. `.env` 文件 `MEDIA_AI_USER` / `MEDIA_AI_PASSWORD`，自动登录

缓存机制：每次使用前通过 `/api/products?limit=1` 验证 cookie 有效性，收到 401/403 自动清除缓存并重新登录。

## 生成文档

```bash
PYTHONPATH=. uv run python scripts/generate_docs.py
```

输出到 `docs/`：
- `openapi.json` — 完整 OpenAPI 3.1 规范
- `openapi.yaml` — YAML 格式
- `media-ai-bridge.postman_collection.json` — Postman 集合

## 安装 Chrome 扩展

1. 打开 `chrome://extensions`
2. 开启右上角"开发者模式"
3. 点击"加载已解压的扩展程序"
4. 选择项目里的 `extension` 目录

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LOG_LEVEL` | `DEBUG` | 日志级别 |
| `MEDIA_AI_BASE_URL` | `http://localhost:3000` | Media AI API 地址 |
| `MEDIA_AI_MEDIA_BASE_URL` | `http://192.168.2.38` | 媒体文件服务器地址 |
| `MEDIA_AI_USER` | — | 登录邮箱 |
| `MEDIA_AI_PASSWORD` | — | 登录密码 |
| `MEDIA_AI_COOKIE` | — | 直接使用 cookie（绕过登录） |

## 任务生命周期

```
pending → claimed → completed
                   └──→ failed
```

1. submit 脚本或插件提交任务（pending）
2. 插件轮询 `/v1/job/claim` 认领任务（claimed）
3. 插件执行浏览器自动化
4. 插件调用 `/v1/job/{id}/result` 或 `/v1/job/{id}/fail`


## 更新 skills

```bash
npx openapi-to-skills docs/openapi.json -o .claude/skills/
npx openapi-to-skills@latest docs/openapi.json -o D:\Code\media\media_ai\.claude\skills
```