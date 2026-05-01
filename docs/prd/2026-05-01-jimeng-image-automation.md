# 即梦（Jimeng）图片生成自动化 PRD

## 1. 概述

### 目标
将即梦图片生成工作流实现为完全自动化的浏览器插件流程：从 media_ai 拉取素材 → 自动操控 Jimeng 网站 UI → 生成图片 → 回传结果。

### 核心流程
1. 从 media_ai 获取素材（人物图、服装图、场景图）和可选的姿态描述
2. 将任务通过本地 Bridge（local_bridge）排队
3. 浏览器插件从 Bridge 认领任务
4. 插件自动操控 Jimeng 网站 UI：选模型 → 上传3张参考图 → 填 Prompt → 生成 → 等待稳定结果 → 上报图片

---

## 2. 系统架构

### 组件关系
```
media_ai API
    ↓ (拉取素材、姿态)
submit_jimeng_image.py (任务准备脚本)
    ↓ (写入 task.md + .media-ai.json)
    ↓ (POST /v1/jobs)
local_bridge (localhost:8765, 任务队列)
    ↑ (GET /v1/job/claim)
chrome-extension (background.js + content-script.js)
    ↓ (自动化 UI 操控)
jimeng.jianying.com (图片生成页面)
```

### 关键端口
- `media_ai`: 默认 `http://localhost:3000`
- `local_bridge`: 默认 `http://127.0.0.1:8765`

---

## 3. 任务准备脚本 (`submit_jimeng_image.py`)

### 输入
- `--style-image-id` / `--style-image-ids-file`：风格图 ID（或文件，每行一个）
- `--scene-id` / `--scene-ids-file`：场景 ID（可选，不提供则自动取 product 和 IP 的场景交集）
- `--pose-id` / `--pose-ids-file`：姿态 ID（可选，用于在 Prompt 中替换 `{pose_description}` 和 `{pose_name}`）
- `--cookie`：media_ai 的认证 cookie（可从 `.env` 或 `MEDIA_AI_COOKIE` 环境变量读取）
- `--prompt-file`：Prompt 模板文件路径（默认 `prompts/08_即梦文生图`）

### Prompt 模板替换
- `{pose_description}` → 姿态的 description（从 media_ai `GET /api/poses/{id}` 获取）
- `{pose_name}` → 姿态的 name

### 输出
每个任务生成以下文件：
- `task.md`：任务描述 + 3张参考图的相对路径 + 最终 Prompt
- `.media-ai.json`：元数据 sidecar（包含 productId、ipId、sceneId、poseId、cookie 等）
- `assets/ip-full-body.{ext}`：人物图（来自 IP 的 fullBodyUrl）
- `assets/product-main.{ext}`：服装主图（来自 Product 的主图）
- `assets/scene-reference.{ext}`：场景参考图（来自 Product 与 IP 场景交集）

### 任务提交
准备好后自动 POST 到 `local_bridge /v1/jobs`，自动等待或 `--prepare-only` 仅准备不提交。

---

## 4. 浏览器插件

### 文件结构
```
extension/
  manifest.json          # MV3，background.service_worker + content_scripts
  background.js          # Service Worker，任务调度、队列轮询、消息中转
  content-script.js      # 注入页面，UI 自动化 + 测试步骤
  popup.html / popup.js  # 插件popup界面
  content-handlers/
    jimeng-image.js      # 即梦图片生成自动化逻辑
    gpt.js               # ChatGPT图片（已有，不修改）
```

### Jimeng 图片生成自动化 (`jimeng-image.js`)

#### Step 1: 导航
跳转到 `https://jimeng.jianying.com/`，等待页面加载包含 "jimeng" 的 URL。

#### Step 2: Tab 选择
点击"图片生成" tab（`role=tab`，text="图片生成"）。

#### Step 3: 模型与比例/分辨率选择
- **模型选择器**：`role=combobox` 的 DIV，点击打开 `role=listbox` 下拉，选择"图片5.0 Lite"
- **比例/分辨率按钮**：`BUTTON`，text 包含"智能比例"，点击打开 radiogroup popover
- **Radio 选择**：直接操作 `input[type=radio]`，选 `value="9:16"` 和 `value="2k"`

#### Step 4: 上传3张参考图
- 人物图（label="人物"）→ 上传到第1个 slot
- 服装图（label="服装"）→ 上传到第2个 slot
- 场景图（label="场景"）→ 上传到第3个 slot

上传方式优先级：
1. 找 `input[type=file]`，通过 DataTransfer 注入 File
2. 找可见的 upload slot，click 触发 file dialog，再注入

#### Step 5: 填写 Prompt
找到 `textarea` 或 `input[placeholder*="描述"]`，填入 job.prompt（触发 InputEvent）。

#### Step 6: 点击生成
找 `button`，text 包含"生成"，点击（需非 disabled）。

#### Step 7: 等待结果
- 建立 baseline：记录当前所有 img.src
- 轮询：新出现的 img（不在 baseline 中，宽高 > 100px）视为候选结果
- **稳定性检查**：连续 8 秒图片 src 不变视为稳定
- 超时：`job.timeoutSeconds` 或默认 10 分钟

#### Step 8: 上报结果
最多选 4 张结果图：
1. fetch img.src（credentials: include）
2. blob → base64
3. POST `{serverUrl}/v1/job/{jobId}/result` → `{ images: [...], logs: [...] }`
4. 失败则 POST `/v1/job/{jobId}/fail`

### 自动化消息流
```
background.js                    content-script.js
    |                                  |
    |--- "controller:runSingleJob" --> |
    |     { serverUrl, job }            |
    |                                  |
    | <-- "content:progress" --------- |
    |     { state, message }           |
    |                                  |
    | <-- "content:finished" -------- |
    |     { jobId, state }             |
    |                                  |
    | <-- "content:failed" ---------- |
    |     { jobId, reason }            |
```

### 测试步骤（S1-S8）
popup 提供独立测试按钮，每个步骤单独验证：
- S1_nav：打开目标页面新 tab
- S2_tab：点击"图片生成" tab
- S3_model：选择模型 + 比例/分辨率
- S4_upload：上传参考图
- S5_prompt：填写 Prompt
- S6_generate：点击生成
- S7_wait：等待稳定结果
- S8_report：上报结果

---

## 5. 测试计划

### 单元测试
- `submit_jimeng_image.py` 参数解析、prompt 替换逻辑
- `jimeng-image.js` 辅助函数（isVisible、waitFor、delay）

### 集成测试
- S1-S8 每步单独手动验证（通过 popup 测试按钮）
- 完整流程：准备任务 → 插件认领 → 自动执行 → 结果回传

### 已知问题
- S3 模型选择逻辑在 Playwright 模拟中通过，但 Chrome extension content script 环境存在时序差异，`document.body.click()` 关下拉后 ratio button 可能仍找不到。尝试：用 `Escape` 键替代 `body.click()` 关下拉。

---

## 6. 非目标（保持现状）

- GPT 图片生成流程：已验证可用，不修改
- local_bridge HTTP API：接口稳定，不修改
- media_ai_client：已验证可用，不修改