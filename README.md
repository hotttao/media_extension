# ChatGPT Image Runner

这个项目提供一个可运行的最小版本，用来在你已经登录的 ChatGPT 网页里自动执行固定的生图任务。

当前实现采用 `Chrome 扩展 + 本地 Python 服务` 的结构：

- 本地服务负责读取 Markdown 测试用例、解析提示词和本地参考图、保存生成结果
- Chrome 扩展负责在已登录的 ChatGPT 页面里上传素材、填入提示词、发送请求、抓取结果

## 目录结构

- `local_bridge/server.py`：本地任务服务
- `local_bridge/media_ai_client.py`：Media AI API 客户端
- `extension/`：Chrome 扩展
- `prompts/`：提示词模板
- `logs/`：运行时日志（git 忽略）
- `runs/`：任务输出结果

## 启动本地服务

```bash
python -m local_bridge.server serve --host 127.0.0.1 --port 8765
```

- 默认监听 `http://127.0.0.1:8765`
- 日志输出到 `logs/server.log`（默认 DEBUG 级别）
- 任务结果保存到 `runs/` 目录

**环境变量：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LOG_LEVEL` | `DEBUG` | 日志级别（DEBUG/INFO/WARNING/ERROR） |
| `MEDIA_AI_BASE_URL` | `http://localhost:3000` | Media AI API 地址 |
| `MEDIA_AI_MEDIA_BASE_URL` | `http://192.168.2.38` | Media AI 媒体文件服务器地址 |

**命令参数：**

| 参数 | 说明 |
|------|------|
| `--host` | 监听地址（默认 `127.0.0.1`） |
| `--port` | 监听端口（默认 `8765`） |
| `--task` | 初始任务文件，可多次指定 |
| `--output-root` | 输出目录（默认 `runs`） |

## API 接口

### GET /health

健康检查。

**响应：**
```json
{ “ok”: true, “now”: “2026-04-28T12:00:00.000Z” }
```

### GET /v1/state

获取所有任务状态。

**响应：**
```json
{
  “jobs”: [
    {
      “id”: “001-task-20260428-120000”,
      “caseFile”: “D:\\...\\task.md”,
      “status”: “pending”,
      “createdAt”: “...”,
      “claimedAt”: null,
      “finishedAt”: null,
      “failureReason”: null,
      “outputDir”: “runs/001-task-20260428-120000”,
      “latestProgress”: { “at”: “...”, “message”: “...” },
      “mediaAi”: { “kind”: “model-image”, ... }
    }
  ]
}
```

### GET /v1/job/claim

从队列认领一个任务。

**请求头：** `X-Worker-Id: worker-1`（可选）

**响应：**
```json
{
  “job”: {
    “id”: “001-task-20260428-120000”,
    “caseFile”: “D:\\...\\task.md”,
    “prompt”: “# 产品名 / IP名 模特图\n\n[图片一：...](assets/model-reference.png)\n[图片二：...](assets/product-main.png)\n\n请根据参考图生成...”,
    “assets”: [
      {
        “index”: 0,
        “label”: “参考图”,
        “name”: “model-reference.png”,
        “mimeType”: “image/png”,
        “url”: “http://127.0.0.1:8765/v1/assets/001-task-20260428-120000/0”
      }
    ],
    “timeoutSeconds”: 900
  }
}
```

### GET /v1/assets/{jobId}/{index}

获取任务资产（图片）。

**响应：** 图片二进制数据。

### POST /v1/jobs

批量提交任务。

**请求体：**
```json
{
  “caseFiles”: [“D:\\path\\to\\task.md”]
}
```

**响应：**
```json
{
  “ok”: true,
  “jobs”: [
    { “id”: “001-task-20260428-120000”, “caseFile”: “...”, “mediaAi”: {...} }
  ]
}
```

### POST /v1/job/{id}/heartbeat

更新任务心跳。

**响应：** `{ “ok”: true, “jobId”: “001-task-20260428-120000” }`

### POST /v1/job/{id}/progress

更新任务进度。

**请求体：**
```json
{ “message”: “正在上传图片...”, “at”: “2026-04-28T12:00:00Z”, “details”: {} }
```

**响应：** `{ “ok”: true }`

### POST /v1/job/{id}/result

提交任务结果图片。

**请求体：**
```json
{
  “images”: [
    { “base64Data”: “...”, “filename”: “result-01.png” },
    { “base64Data”: “...”, “filename”: “result-02.png” }
  ],
  “assistantResponse”: “生成完成”,
  “logs”: []
}
```

**响应：**
```json
{
  “ok”: true,
  “savedFiles”: [“result-01.png”, “result-02.png”],
  “skippedFiles”: [],
  “mediaAiResults”: [{ “kind”: “style-image”, “uploaded”: {...}, “saved”: {...} }]
}
```

### POST /v1/job/{id}/fail

标记任务失败。

**请求体：**
```json
{ “reason”: “超时” }
```

**响应：** `{ “ok”: true }`

### POST /v1/job/{id}/requeue

重新排队任务。

**响应：** `{ “ok”: true, “jobId”: “...”, “status”: “pending” }`

### POST /v1/job/{id}/cancel

取消任务。

**响应：** `{ “ok”: true, “jobId”: “...”, “status”: “canceled” }`

### POST /v1/jobs/cancel

取消所有 pending 状态的任务。

**响应：**
```json
{
  “ok”: true,
  “canceled”: [
    { “jobId”: “001-task-20260428-120000”, “status”: “canceled” },
    { “jobId”: “002-task-20260428-120001”, “status”: “canceled” }
  ]
}
```

### POST /v1/single/model-image

创建模特图任务。

**请求体：**
```json
{
  “productId”: “3813528280213094793”,
  “ipId”: “981cd79c-5973-429a-8edf-dff3eda45014”,
  “force”: false
}
```

或仅提供 `modelImageId`（自动解析 productId 和 ipId）：

```json
{
  “modelImageId”: “309d6c4c-19a3-46f0-9317-a60e1ee21cf7”,
  “force”: false
}
```

**响应：**
```json
{
  “ok”: true,
  “job”: {
    “id”: “001-task-20260428-120000”,
    “caseFile”: “runs/.../task.md”,
    “mediaAi”: {
      “kind”: “model-image”,
      “productId”: “3813528280213094793”,
      “productName”: “2026夏季新款女韩系穿搭...”,
      “ipId”: “981cd79c-5973-429a-8edf-dff3eda45014”,
      “productMainImageUrl”: “http://192.168.2.38/...”
    }
  }
}
```

### POST /v1/single/style-image

创建定妆图任务。

**请求体：**
```json
{
  “modelImageId”: “309d6c4c-19a3-46f0-9317-a60e1ee21cf7”,
  “poseId”: “4df51547-928f-44b6-ad5a-0f7807c0106c”,
  “force”: false
}
```

**响应：**
```json
{
  “ok”: true,
  “job”: {
    “id”: “001-task-20260428-120000”,
    “caseFile”: “runs/.../task.md”,
    “mediaAi”: {
      “kind”: “style-image”,
      “modelImageId”: “309d6c4c-...”,
      “poseId”: “4df51547-...”,
      “poseName”: “举手机自拍”,
      ...
    }
  }
}
```

### POST /v1/single/first-frame-image

创建首帧图任务。

**请求体：**
```json
{
  “styleImageId”: “d54f8c2a-9c13-4a7e-b8e1-4f3a2b1c5d4e”,
  “sceneId”: “3d30e5eb-292d-4574-95f6-abb25e00fc6c”,
  “force”: false
}
```

**响应：**
```json
{
  “ok”: true,
  “job”: {
    “id”: “001-task-20260428-120000”,
    “caseFile”: “runs/.../task.md”,
    “mediaAi”: { “kind”: “first-frame-image”, ... }
  }
}
```

## 输出结果

每个任务会在 `runs/<job-id>/` 下生成：

- `prompt.md`：实际发送的提示词
- `metadata.json`：任务元信息
- `logs.json`：每一步进度日志，包含 assistant 回复节点信息和图片源 URL
- `result-01.png` 等：抓取到的生成结果
- `failure.json`：如果任务失败，会记录失败原因

## 运行前提

1. 本机已安装 Python 3.11+
2. 使用 Chrome 或兼容 Chromium 的浏览器
3. 你已经在浏览器里登录 ChatGPT Plus
4. 在开始自动化前，手动打开一个新的 ChatGPT 对话，并切换到你想用的图片生成模型或图片生成模式

## 启动步骤

### 1. 启动本地服务

```powershell
python local_bridge\server.py serve --task test_case\模特图.md
```

默认会监听 `http://127.0.0.1:8765`，并把结果保存到 `runs/` 目录。

### 2. 安装扩展

1. 打开 `chrome://extensions`
2. 开启右上角”开发者模式”
3. 点击”加载已解压的扩展程序”
4. 选择当前项目里的 `extension` 目录

### 3. 执行任务

1. 打开已经登录的 ChatGPT 页面
2. 手动切到图片生成模型或图片生成模式
3. 点击浏览器工具栏里的扩展图标
4. 确认服务地址为 `http://127.0.0.1:8765`
5. 点击 `Start`

扩展会自动：

- 读取待执行任务
- 上传 Markdown 里引用的参考图
- 填入整理后的提示词
- 发送请求
- 等待生成完成
- 把结果图片回传给本地服务保存

## 当前限制

- 这是一个网页自动化 MVP，仍然依赖 ChatGPT 当前网页结构
- 模型切换这一步没有强行自动化，建议你先手动切好模型再点击 `Start`
- 如果 ChatGPT 调整了输入框、上传控件或消息布局，扩展里的选择器可能需要更新

## 解析测试用例

可以先用下面的命令检查 Markdown 是否被正确解析：

```powershell
python local_bridge\server.py inspect test_case\模特图.md
```


## Media AI 批量提交脚本

提供两个脚本用于批量提交图片生成任务到本地 GPT 图片队列：

- `scripts/submit_media_ai_model_images.py`：提交模特图任务
- `scripts/submit_media_ai_style_images.py`：提交定妆图任务

### 通用参数

| 参数 | 说明 |
|------|------|
| `--base-url` | Media AI API 地址（默认从环境变量或配置读取） |
| `--bridge-url` | 本地 bridge 服务地址（默认 `http://127.0.0.1:8765`） |
| `--cookie` | Media AI 浏览器 Cookie header 值 |
| `--cookie-file` | 包含 Cookie 的文件 |
| `--env-file` | 环境变量文件（默认 `.env`） |
| `--no-embed-cookie` | 不在 task sidecars 中存储认证 cookie |
| `--timeout` | API 请求超时秒数（默认 120） |
| `--prepare-only` | 仅创建任务文件，不提交到队列 |
| `--no-auto-bridge` | 不自动启动本地 bridge（如果不可用） |
| `--no-wait` | 提交后立即退出，不等待完成 |
| `--poll-interval` | 轮询间隔秒数（默认 15） |
| `--wait-timeout` | 等待任务完成的最大秒数，0 表示不限（默认 180） |
| `--output-root` | 输出目录（默认 `runs/media-ai-*-queue-YYYYMMDD-HHMMSS`） |

### submit_media_ai_model_images.py

提交模特图任务到 GPT 图片队列。

```
python scripts/submit_media_ai_model_images.py [参数]
```

**专用参数：**

| 参数 | 说明 |
|------|------|
| `--prompt-file` | 提示词文件（默认 `prompts/03_模特图.md`） |
| `--ip-id` | 虚拟 IP ID 筛选，可多次指定 |
| `--product-id` | 产品 ID 筛选，可多次指定 |
| `--product-ids-file` | 产品 ID 列表文件（每行一个 ID，或 JSON 数组） |
| `--target-audience` | 目标受众筛选（MENS/WOMENS/KIDS） |
| `--search` | 从 `/api/products` 搜索的关键词 |
| `--limit` | 最多检查的产品数量 |
| `--no-detail-images` | 不下载细节图 |
| `--max-detail-images` | 最大细节图数量（默认 6） |
| `--upload-subdir` | 上传子目录（默认 `model-images`） |

**示例：**

```powershell
# 使用环境变量登录，检查所有产品，提交任务并等待完成
python scripts/submit_media_ai_model_images.py --env-file .env

# 仅准备任务文件，不提交
python scripts/submit_media_ai_model_images.py --prepare-only

# 提交后立即退出，不等待
python scripts/submit_media_ai_model_images.py --no-wait

# 指定产品ID，搜索特定产品
python scripts/submit_media_ai_model_images.py --search “T恤” --limit 10

# 设置更长的等待超时（5分钟）
python scripts/submit_media_ai_model_images.py --wait-timeout 300
```

### submit_media_ai_style_images.py

提交定妆图任务到 GPT 图片队列。

```
python scripts/submit_media_ai_style_images.py [参数]
```

**专用参数：**

| 参数 | 说明 |
|------|------|
| `--prompt-file` | 提示词文件（默认 `prompts/04_定妆图.md`） |
| `--product-id` | 产品 ID 筛选，可多次指定 |
| `--product-ids-file` | 产品 ID 列表文件 |
| `--model-image-id` | 模特图 ID（指定单个） |
| `--pose-id` | 姿势 ID（指定单个） |
| `--pose-ids-file` | 姿势 ID 列表文件 |
| `--target-audience` | 目标受众筛选 |
| `--search` | 从 `/api/products` 搜索的关键词 |
| `--limit` | 最多检查的产品数量 |
| `--pose-limit` | 每个产品最多姿势数量 |
| `--upload-subdir` | 上传子目录 |

**示例：**

```powershell
# 使用环境变量登录，提交定妆图任务
python scripts/submit_media_ai_style_images.py --env-file .env

# 指定产品ID和姿势文件
python scripts/submit_media_ai_style_images.py --product-id 12345 --pose-ids-file pose_ids.txt

# 提交后立即退出
python scripts/submit_media_ai_style_images.py --no-wait
```

### submit_media_ai_first_frame_images.py

提交首帧图任务到 GPT 图片队列。将模特定妆照放置到不同场景中生成首帧图。

```
python scripts/submit_media_ai_first_frame_images.py [参数]
```

**专用参数：**

| 参数 | 说明 |
|------|------|
| `--prompt-file` | 提示词文件（默认 `prompts/05_首帧图.md`） |
| `--product-id` | 产品 ID 筛选，可多次指定 |
| `--product-ids-file` | 产品 ID 列表文件 |
| `--ip-id` | 虚拟 IP ID 筛选 |
| `--style-image-id` | 定妆图 ID 筛选，可多次指定 |
| `--scene-id` | 场景 ID 筛选，可多次指定 |
| `--scene-ids-file` | 场景 ID 列表文件 |
| `--target-audience` | 目标受众筛选 |
| `--search` | 从 `/api/products` 搜索的关键词 |
| `--limit` | 最多检查的产品数量 |
| `--scene-limit` | 最多选择的场景数量 |
| `--frames-per-style` | 每个定妆图生成的首帧图数量（默认 5） |
| `--upload-subdir` | 上传子目录 |

**示例：**

```powershell
# 使用环境变量登录，为所有产品生成首帧图（每个定妆照5个场景）
python scripts/submit_media_ai_first_frame_images.py --env-file .env

# 指定产品ID和场景数量
python scripts/submit_media_ai_first_frame_images.py --product-id 12345 --scene-limit 10

# 每个定妆图生成3个首帧图
python scripts/submit_media_ai_first_frame_images.py --frames-per-style 3

# 仅准备任务文件，不提交
python scripts/submit_media_ai_first_frame_images.py --prepare-only
```

## 更新 skills

```powershell
npx openapi-to-skills D:\Code\media\media_ai\docs\openapi.json -o .codex\skills
```