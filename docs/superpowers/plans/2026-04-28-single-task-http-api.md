# 单任务 HTTP 接口实现计划

> **Goal:** 在 bridge 服务端新增三个 HTTP 接口，支持通过指定 ID 直接提交单个生图任务
>
> **Architecture:** 抽取共享的任务构建逻辑到 `local_bridge/single_task.py`，脚本和 server 共用同一份核心逻辑，server 新增三个端点调用这些函数
>
> **Tech Stack:** Python, http.server, argparse

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `local_bridge/single_task.py` (新建) | 单任务构建核心逻辑，可被脚本和 server 复用 |
| `local_bridge/server.py` (修改) | 新增三个 POST 端点 |
| `scripts/submit_media_ai_model_images.py` (修改) | 改用 `single_task.py` 中的 `build_model_task` |
| `scripts/submit_media_ai_style_images.py` (修改) | 改用 `single_task.py` 中的 `build_style_task` |
| `scripts/submit_media_ai_first_frame_images.py` (修改) | 改用 `single_task.py` 中的 `build_first_frame_task` |

---

## Task 1: 创建 `local_bridge/single_task.py`

**文件:**
- 新建: `local_bridge/single_task.py`

从现有的 `submit_media_ai_model_images.py`、`submit_media_ai_style_images.py`、`submit_media_ai_first_frame_images.py` 中提取共用的任务构建逻辑为可复用函数。

### 必须包含的函数

**共用工具函数:**
- `request_json(method, url, *, cookie=None, body=None, timeout=120)` - HTTP JSON 请求
- `download_file(url, target, *, cookie=None, timeout=120)` - 下载文件
- `resolve_media_url(base_url, value)` - 解析媒体 URL
- `extension_from_url(url, fallback=".png")` - 从 URL 获取文件扩展名
- `slugify(value)` - slug 化字符串
- `read_text(path: pathlib.Path) -> str` - 读取文本文件
- `guess_mime_type(path: pathlib.Path) -> str` - 猜测 MIME 类型
- `sha256_bytes(data: bytes) -> str` - 计算 SHA256
- `load_media_ai_sidecar(case_path: pathlib.Path) -> dict | None` - 加载 sidecar

**`build_model_image_task`** - 模特图任务
```
参数:
  base_url: str
  product_id: str
  ip_id: str
  cookie: str | None
  output_root: pathlib.Path
  prompt: str

逻辑:
  1. 调用 GET {base_url}/api/products/{product_id} 获取 product
  2. 调用 GET {base_url}/api/ips/{ip_id} 获取 ip
  3. 验证 product 有 mainImageUrl，ip 有 fullBodyUrl
  4. 下载图片到 output_root/assets/
  5. 生成 task.md 和 .media-ai.json sidecar
  6. 返回 case_path

sidecar kind: "model-image"
```

**`build_style_image_task`** - 定妆图任务
```
参数:
  base_url: str
  model_image_id: str
  pose_id: str
  cookie: str | None
  output_root: pathlib.Path
  prompt: str

逻辑:
  1. 调用 GET {base_url}/api/products/{product_id}/generated-materials 获取 model_image 详情（含 productId）
  2. 调用 GET {base_url}/api/materials?type=POSE 获取 pose 详情
  3. 验证 model_image 有 url，pose 有 url
  4. 下载图片到 output_root/assets/
  5. 生成 task.md 和 .media-ai.json sidecar
  6. 返回 case_path

sidecar kind: "style-image"
```

**`build_first_frame_task`** - 首帧图任务
```
参数:
  base_url: str
  style_image_id: str
  scene_id: str
  cookie: str | None
  output_root: pathlib.Path
  prompt: str

逻辑:
  1. 调用 GET {base_url}/api/products/{product_id}/generated-materials 获取 style_image 详情（含 productId, ipId）
  2. 调用相关接口获取 scene 详情
  3. 下载 style_image 和 scene 图片
  4. 生成 task.md 和 .media-ai.json sidecar
  5. 返回 case_path

sidecar kind: "first-frame-image"
```

**注意:** prompt 从服务端配置文件读取，配置文件路径固定为 `prompts/03_模特图.md`、`04_定妆图.md`、`05_首帧图.md`

---

## Task 2: 修改 `scripts/submit_media_ai_model_images.py`

**文件:**
- 修改: `scripts/submit_media_ai_model_images.py`

将 `build_task_file` 函数替换为调用 `single_task.build_model_image_task()`。其余逻辑（fetch_products, fetch_ips, 遍历组合生成所有任务）保持不变。

需要确保 import 路径正确处理（可能需要将 `single_task.py` 放在可 import 的位置或调整 import 方式）。

---

## Task 3: 修改 `scripts/submit_media_ai_style_images.py`

**文件:**
- 修改: `scripts/submit_media_ai_style_images.py`

将 `build_task_file` 函数替换为调用 `single_task.build_style_image_task()`。

---

## Task 4: 修改 `scripts/submit_media_ai_first_frame_images.py`

**文件:**
- 修改: `scripts/submit_media_ai_first_frame_images.py`

将 `build_task_file` 函数替换为调用 `single_task.build_first_frame_task()`。

---

## Task 5: 在 `local_bridge/server.py` 添加三个端点

**文件:**
- 修改: `local_bridge/server.py`

在 `RequestHandler.do_POST()` 中新增三个路由，使用 `re.fullmatch` 匹配路径：

| 路径 | 端点 | 请求体 |
|------|------|--------|
| `/v1/single/model-image` | 单个模特图 | `{"modelImageId": "xxx"}` 或 `{"productId": "xxx", "ipId": "yyy"}` |
| `/v1/single/style-image` | 单个定妆图 | `{"modelImageId": "xxx", "poseId": "yyy"}` |
| `/v1/single/first-frame-image` | 单个首帧图 | `{"styleImageId": "xxx", "sceneId": "yyy"}` |

**共用逻辑:**
1. 解析请求体获取参数
2. 从请求头 `Cookie` 获取认证信息，如果没有则从环境变量 `MEDIA_AI_COOKIE` 获取
3. 从 `prompts/03_模特图.md`、`04_定妆图.md`、`05_首帧图.md` 读取 prompt
4. 调用对应的 `single_task.build_*_task()` 函数生成 task.md
5. 调用 `self.server.store.add_jobs([case_path])` 提交到队列
6. 返回 `{"ok": true, "job": {...}}`

**响应格式:**
```json
{
  "ok": true,
  "job": {
    "id": "001-model-image-20260428",
    "caseFile": "/path/to/task.md",
    "mediaAi": { ... }
  }
}
```

**错误处理:**
- 缺少必需参数返回 400
- 找不到资源返回 404
- 生成失败返回 500
