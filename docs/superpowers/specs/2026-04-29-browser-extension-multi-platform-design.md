# 浏览器插件多平台扩展设计方案

## 背景

现有浏览器插件（`extension/`）配合 `local_bridge` 实现 ChatGPT 页面自动提交生图任务。现在需要扩展支持即梦（jimeng.jianying.com）的生图和生视频任务，同时保持架构可扩展以便后续接入更多平台。

核心原则：
1. **GPT 代码尽可能不修改**——现有 job 格式和处理逻辑保持不变
2. **即梦 job 格式与 GPT 保持一致**——`styleImageId` + `sceneId`，Extension 接口不变
3. **local_bridge 侧完成平台相关转换**——`styleImageId` 查表得到 `productId` + `ipId`

---

## 1. Job 格式扩展

### 1.1 local_bridge → Extension 的 Job 格式

`/v1/job/claim` 返回的 job 增加两个字段：

```json
{
  "id": "job-001",
  "platform": "jimeng_image",
  "targetUrl": "https://jimeng.jianying.com/ai-tool/home/?type=image&workspace=0",
  "prompt": "完整提示词",
  "assets": [{"index": 0, "label": "styleImage", "name": "xxx.jpg", "url": "..."}],
  "styleImageId": "虚拟IP全身图的styleImageID",
  "sceneId": "场景ID",
  "timeoutSeconds": 900
}
```

- `platform`：平台标识。`gpt` 或 absent 表示 GPT 生图；`jimeng_image` 表示即梦生图；`jimeng_video` 表示即梦生视频
- `targetUrl`：Extension 应打开的目标页面 URL，由 `local_bridge` 根据 platform 生成，不再 hardcode 在插件中
- GPT job 保持原有格式（无 `platform` 字段或 `platform: "gpt"`），Extension 现有逻辑不变

### 1.2 即梦 job 的生成逻辑（local_bridge 侧）

`local_bridge` 在生成即梦 job 时：
1. 根据 `styleImageId` 查询 `style_image` 表，得到 `productId` + `ipId`
2. 查询 `scene` 表得到场景信息
3. 根据 `platform` 类型（`jimeng_image` / `jimeng_video`）使用对应的 prompt 模板
4. `assets` 数组格式与 GPT job 完全一致（Extension 已知如何处理）
5. `targetUrl` 根据 platform 设置为对应的即梦页面 URL

### 1.3 Extension → local_bridge 的结果格式

Job 完成后，Extension 向 `/v1/job/{id}/result` 提交结果，格式与 GPT 完全一致：

```json
{
  "images": [
    {"filename": "1.jpg", "base64Data": "...", "sourceUrl": "..."},
    {"filename": "2.jpg", "base64Data": "...", "sourceUrl": "..."},
    {"filename": "3.jpg", "base64Data": "...", "sourceUrl": "..."},
    {"filename": "4.jpg", "base64Data": "...", "sourceUrl": "..."}
  ],
  "logs": [...]
}
```

`local_bridge` 保存时根据 `platform` 字段决定如何解析 `styleImageId` + `sceneId` 写入对应的数据库字段，保证 trace 逻辑兼容。

---

## 2. Background Script 平台路由

### 2.1 领取 Job

Background 通过 `/v1/job/claim` 领取 job，领取时不区分 platform，轮询到哪个就处理哪个。

### 2.2 打开目标页面

根据 `job.targetUrl` 动态决定打开哪个页面：

```javascript
const tab = await chrome.tabs.create({ url: job.targetUrl });
```

不再 hardcode ChatGPT URL。所有平台路由信息由 `local_bridge` 的 job 数据提供。

### 2.3 消息转发

Background 将 job 信息转发给 content script：
```javascript
chrome.tabs.sendMessage(tabId, {
  type: "controller:runSingleJob",
  serverUrl,
  job,
});
```

Content script 收到 job 后，根据 `job.platform` 选择对应的 handler。

---

## 3. Content Script 平台分支

### 3.1 Handler 分发

`content-script.js` 的 `runJob(job)` 函数根据 `job.platform` 分发到不同 handler：

| `job.platform` | Handler |
|---|---|
| `undefined` / `"gpt"` | `runGptJob`（现有逻辑，文件名改为 `handlers/gpt.js`） |
| `"jimeng_image"` | `runJimengImageJob`（新增，文件名 `handlers/jimeng_image.js`） |
| `"jimeng_video"` | `runJimengVideoJob`（新增，文件名 `handlers/jimeng_video.js`） |

各 handler 对外接口一致：接收 job 对象，执行页面操作，最后都调用 `serializeImages` + `postJson(..., /result)` 上报结果。

### 3.2 即梦生图 Handler（jimeng_image）

流程：
1. 打开即梦页面（`targetUrl`），等待页面加载
2. 点击"图片生成"模式（页面底部选择）
3. 选择"图片5.0 Lite 9:16 2K"模型
4. 上传三张参考图（人物、服装、场景）：通过 `assets` 数组获取图片 URL → fetch → 转为 File → 上传
5. 填入 prompt
6. 点击生成按钮
7. 轮询等待图片生成完成（检测页面中的图片元素稳定性）
8. 序列化所有生成的图片（最多4张）
9. 调用 `postJson(..., /result)` 上报结果

### 3.3 即梦生视频 Handler（jimeng_video）

流程：
1. 打开即梦页面（`targetUrl`），等待页面加载
2. 点击"视频生成"模式（页面底部选择）
3. 选择"Seedance1.0 首尾帧"模型
4. 上传首帧图（从 `assets` 获取）
5. 填入动作描述（从 job 的 `movement` 字段获取，或从 `movementId` 查询）
6. 填入 prompt
7. 点击生成按钮
8. 轮询等待视频生成完成（检测页面中的视频元素）
9. 序列化视频文件
10. 调用 `postJson(..., /result)` 上报结果

### 3.4 图片/视频稳定性检测

即梦的生成结果可能分次返回（先生成一个，过一会儿再生成更多）。等待逻辑：
- 轮询页面 DOM，收集所有新出现的图片/视频元素
- 检测元素 src 稳定性（8 秒内 src 不变视为完成）
- 支持超时（`timeoutSeconds`）

---

## 4. Popup UI

### 4.1 布局

每个平台独立面板，按行排列：
```
┌─────────────────────────────────┐
│ GPT                             │
│ [Start] [Stop] [Cancel All]     │
│ Pending: 0  Running: 0          │
│ Completed: 12  Failed: 0       │
│ Status: Idle                    │
├─────────────────────────────────┤
│ 即梦图片                         │
│ [Start] [Stop] [Cancel All]     │
│ Pending: 3  Running: 1          │
│ Completed: 5   Failed: 0        │
│ Status: Running job-xxx          │
├─────────────────────────────────┤
│ 即梦视频                         │
│ [Start] [Stop] [Cancel All]     │
│ Pending: 0  Running: 0          │
│ Completed: 2   Failed: 0         │
│ Status: Idle                    │
└─────────────────────────────────┘
```

### 4.2 数据来源

- **Start/Stop**：发送 `popup:start` / `popup:stop` 消息，带 platform 参数
- **Cancel All**：发送 `popup:cancelAll` 消息，带 platform 参数，Background 调用 `POST /v1/jobs/cancel` 时附上 platform 过滤参数
- **统计数据**：Background 定期同步各平台 job 状态到 popup，popup 也可通过 `popup:getState` 获取

### 4.3 状态展示

每平台显示：
- 该平台 Start/Stop 按钮
- Cancel All 按钮（取消该平台所有 pending 状态的 job）
- 各状态计数（Pending / Running / Completed / Failed）
- 当前 job ID（如有）
- 错误信息（如有）

---

## 5. Manifest 权限扩展

`manifest.json` 的 `host_permissions` 新增即梦域名：

```json
"host_permissions": [
  "https://chatgpt.com/*",
  "https://chat.openai.com/*",
  "https://*.openai.com/*",
  "https://*.oaiusercontent.com/*",
  "https://*.blob.core.windows.net/*",
  "https://jimeng.jianying.com/*",
  "http://127.0.0.1:8765/*",
  "http://localhost:8765/*"
]
```

Content scripts 的 `matches` 数组同样加上即梦域名。

---

## 6. local_bridge 改动要点

1. **Job 生成时**：即梦 job 增加 `platform` 和 `targetUrl` 字段，`to_public_dict()` 方法返回这两个字段
2. **styleImageId 查表**：生成即梦 job 时，用 `styleImageId` 查 `style_image` 表得到 `productId` + `ipId`，内嵌到 job 数据中（不暴露给 Extension 接口，但可用于保存结果时关联）
3. **结果保存时**：根据 `platform` 字段决定如何写库——GPT 写 `styleImageId`，即梦写 `ipId` + `productId`（字段在数据库层面已兼容，nullable）

---

## 7. 文件变更清单

```
extension/
  manifest.json          # + jimeng host_permissions, content_script matches
  background.js          # + platform 参数传递, cancelAll 支持
  popup.html             # 重写，按平台分组
  popup.js               # 重写，按平台独立控制
  content-script.js      # 拆分为入口 + handlers/
    handlers/
      gpt.js             # 现有逻辑移入
      jimeng_image.js    # 新增
      jimeng_video.js    # 新增

local_bridge/
  server.py              # Job.to_public_dict() 增加 platform/targetUrl
  (其他文件按需修改)
```

---

## 8. 未纳入本次设计的事项

- 即梦生图的图片选择保存功能（用户已确认默认保存4张，后续本地筛选）
- 其他平台的支持（本设计已考虑可扩展性，新平台只需在 local_bridge 加 job 生成逻辑 + extension 加 handler）