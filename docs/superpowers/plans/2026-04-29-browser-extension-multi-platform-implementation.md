# 浏览器插件多平台扩展实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 扩展浏览器插件支持即梦生图和生视频任务，实现平台可插拔架构，Popup 按平台独立控制状态。

**Architecture:**
- Content script 按 `job.platform` 分发到独立 handler（GPT/即梦图片/即梦视频），共用基础设施（http fetch、DOM 检测、结果上报）
- Background 根据 `job.targetUrl` 动态打开标签页，不再 hardcode ChatGPT URL
- Popup 按平台分组显示，各平台独立 Start/Stop/Cancel All
- local_bridge 在 job 数据中注入 `platform` 和 `targetUrl`，Extension 接口不变

**Tech Stack:** Chrome Extension (Manifest V3), JavaScript, local_bridge Python HTTP server

---

## 文件变更概览

```
extension/
  manifest.json          # + jimeng host_permissions, content_script matches
  background.js          # + platform 参数传递, cancelAll 支持
  popup.html             # 重写，按平台分组
  popup.js               # 重写，按平台独立控制
  content-script.js      # 改为入口，按 platform 分发
  content-handlers/
    gpt.js               # 从 content-script.js 移出现有逻辑
    jimeng-image.js      # 新增
    jimeng-video.js      # 新增

local_bridge/
  server.py              # Job.to_public_dict() 增加 platform/targetUrl
```

---

## Task 1: 创建 content-handlers/ 目录结构，迁移 GPT handler

**Files:**
- Create: `extension/content-handlers/gpt.js`
- Modify: `extension/content-script.js:1-50`（移除 `runJob` 逻辑，改为分发）

- [ ] **Step 1: 创建 `extension/content-handlers/` 目录和 `gpt.js`**

```javascript
// extension/content-handlers/gpt.js
// GPT 生图 handler - 从现有 content-script.js 移出的逻辑

function findComposer() {
  return composerCandidates().find((element) => isVisible(element)) || null;
}

function getComposerText(composer) {
  if ("value" in composer) {
    return String(composer.value || "");
  }
  return String(composer.innerText || composer.textContent || "");
}

function clearComposer(composer) {
  // ... existing implementation
}

function setComposerText(composer, text) {
  // ... existing implementation
}

function findSendButton(composer) {
  // ... existing implementation
}

function dispatchEnter(composer) {
  // ... existing implementation
}

function findComposerForm(composer) {
  return composer.closest("form");
}

function collectVisibleButtons(limit = 15) {
  // ... existing implementation
}

function getElementPath(element) {
  // ... existing implementation
}

function describeButton(button) {
  // ... existing implementation
}

async function ensureFileInput() {
  // ... existing implementation
}

async function fetchAssetAsFile(asset) {
  // ... existing implementation
}

async function uploadAssets(job) {
  // ... existing implementation
}

function composerCandidates() {
  return [
    document.querySelector("textarea"),
    document.querySelector("#prompt-textarea"),
    document.querySelector("div[contenteditable='true'][role='textbox']"),
    document.querySelector("div[contenteditable='true'][data-lexical-editor='true']"),
  ].filter(Boolean);
}

function sanitizeText(value, maxLength = 240) {
  return String(value || "").replace(/\s+/g, " ").trim().slice(0, maxLength);
}

function isVisible(element) {
  // ... existing implementation
}

async function waitFor(predicate, options = {}) {
  // ... existing implementation
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function getAssistantTurnElements() {
  return Array.from(
    document.querySelectorAll("section[data-turn='assistant'][data-testid^='conversation-turn-']")
  ).filter((element) => isVisible(element));
}

function collectImageEntries(root = document) {
  // ... existing implementation
}

function collectImageKeys(root = document) {
  return new Set(collectImageEntries(root).map((entry) => entry.key));
}

function getImageSearchRoot() {
  return document.querySelector("main") || document;
}

function collectAllAssistantImageKeys() {
  // ... existing implementation
}

function describeAssistantTurn(turnElement, imageEntries) {
  // ... existing implementation
}

async function waitForSubmissionEffect(composer, baselineAssistantCount) {
  // ... existing implementation
}

async function submitPrompt(composer, baselineAssistantCount) {
  // ... existing implementation
}

async function waitForAssistantResponseImages(baselineAssistantImageKeys, timeoutMs) {
  // ... existing implementation
}

async function waitForGeneratedImagesAnywhere(baselineImageKeys, timeoutMs) {
  // ... existing implementation
}

function blobToBase64(blob) {
  // ... existing implementation
}

function extensionFromMimeType(mimeType) {
  // ... existing implementation
}

async function serializeImages(entries) {
  // ... existing implementation
}

async function waitForUploadComplete(expectedCount) {
  // ... existing implementation
}

// 主入口 - runGptJob
async function runGptJob(job, serverUrl) {
  // 从 content-script.js 的 runJob 中 GPT 相关逻辑移入
  const logs = [];

  const record = async (message, details = null) => {
    const at = new Date().toISOString();
    const entry = { at, message };
    if (details !== null && details !== undefined) {
      entry.details = details;
    }
    logs.push(entry);
    await notifyProgress(message);
    await sendProgress(serverUrl, message, at, details);
  };

  try {
    await record(`Preparing ${job.id}`);
    const composer = await waitFor(() => findComposer(), { timeoutMs: 120000, label: "prompt composer" });

    await record("Uploading reference images");
    await uploadAssets(job);

    await record("Writing prompt");
    setComposerText(composer, job.prompt);
    await delay(500);

    const baselineAssistantCount = getAssistantTurnElements().length;
    const baselineAssistantImageKeys = collectAllAssistantImageKeys();
    const baselinePageImageKeys = collectImageKeys(getImageSearchRoot());

    await record("Submitting job", {
      composerPath: getElementPath(composer),
      visibleButtons: collectVisibleButtons(),
    });

    const submitResult = await submitPrompt(composer, baselineAssistantCount);
    await record("Submit triggered", submitResult);
    if (!submitResult.submitted) {
      throw new Error("Prompt did not submit");
    }

    await record("Waiting for generated images");
    let responseCapture = null;
    try {
      responseCapture = await waitForAssistantResponseImages(
        baselineAssistantImageKeys,
        job.timeoutSeconds ? job.timeoutSeconds * 1000 : DEFAULT_TIMEOUT_MS
      );
    } catch (_error) {
      responseCapture = await waitForGeneratedImagesAnywhere(
        baselinePageImageKeys,
        job.timeoutSeconds ? job.timeoutSeconds * 1000 : DEFAULT_TIMEOUT_MS
      );
      await record("Assistant-scope detection missed images; used page-wide fallback", {
        imageCount: responseCapture.images.length,
      });
    }

    await record(`Found ${responseCapture.images.length} generated image(s)`, {
      assistantTurn: responseCapture.assistantTurn,
    });

    const serializedImages = await serializeImages(responseCapture.images);
    await record("Saving results to local bridge", {
      imageCount: serializedImages.length,
    });

    await postJson(`${serverUrl}/v1/job/${encodeURIComponent(job.id)}/result`, {
      images: serializedImages,
      logs,
    });

    controllerState.lastError = null;
    controllerState.lastMessage = `Completed ${job.id}`;
    await chrome.runtime.sendMessage({ type: "content:finished", jobId: job.id, state: { ...controllerState } });
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    logs.push({ at: new Date().toISOString(), message: `Failed: ${reason}` });
    try {
      await postJson(`${serverUrl}/v1/job/${encodeURIComponent(job.id)}/fail`, {
        reason,
        logs,
      });
    } catch (_postError) {
      // Ignore reporting errors.
    }
    controllerState.lastError = reason;
    controllerState.lastMessage = `Failed ${job.id}`;
    await chrome.runtime.sendMessage({ type: "content:failed", jobId: job.id, reason, state: { ...controllerState } });
  }
}

module.exports = { runGptJob };
```

- [ ] **Step 2: 修改 `extension/content-script.js` 作为入口文件**

替换文件开头部分，移除所有 handler 实现，仅保留通用基础设施（`delay`, `isVisible`, `getElementPath`, `notifyProgress`, `sendProgress`, `postJson`, `bridgeFetch`, `serializeImages` 等），添加 `runJob(job, serverUrl)` 分发逻辑：

```javascript
// extension/content-script.js
// 入口文件：根据 job.platform 分发到对应 handler

const DEFAULT_TIMEOUT_MS = 15 * 60 * 1000;
const SUBMISSION_EFFECT_TIMEOUT_MS = 120 * 000;
const POLL_INTERVAL_MS = 5000;
const HEARTBEAT_INTERVAL_MS = 20000;

const controllerState = {
  running: false,
  busy: false,
  serverUrl: "http://127.0.0.1:8765",
  currentJobId: null,
  lastMessage: "Idle",
  lastError: null,
};

// 通用基础设施（从原有代码保留）
// ... delay, isVisible, getElementPath, sanitizeText, notifyProgress, sendProgress, postJson, bridgeFetch ...

// 根据 platform 分发到对应 handler
async function runJob(job, serverUrl) {
  const platform = job.platform || "gpt";
  if (platform === "gpt") {
    const { runGptJob } = require("./content-handlers/gpt.js");
    await runGptJob(job, serverUrl);
  } else if (platform === "jimeng") {
    const { runJimengImageJob } = require("./content-handlers/jimeng-image.js");
    await runJimengImageJob(job, serverUrl);
  } else {
    throw new Error(`Unknown platform: ${platform}`);
  }
}

// 原有消息监听保持不变
// chrome.runtime.onMessage.addListener(...)
```

- [ ] **Step 3: 验证拆分后的 GPT handler 逻辑完整性**

确保 `content-handlers/gpt.js` 中的所有函数引用都是自包含的，没有 external dependencies on `content-script.js` 中的其他函数（除了显式传入的 job 和 serverUrl）。

Run: N/A (浏览器扩展需要在浏览器中测试，暂无自动化测试框架)

- [ ] **Step 4: 提交**

```bash
git add extension/content-script.js extension/content-handlers/gpt.js
git commit -m "refactor: extract GPT handler to content-handlers/gpt.js"
```

---

## Task 2: 创建即梦图片 handler（jimeng-image.js）

**Files:**
- Create: `extension/content-handlers/jimeng-image.js`

- [ ] **Step 1: 编写 `jimeng-image.js` 基础框架**

```javascript
// extension/content-handlers/jimeng-image.js

const DEFAULT_TIMEOUT_MS = 15 * 60 * 1000;

async function runJimengImageJob(job, serverUrl) {
  // job.platform === "jimeng"
  // job.targetUrl: https://jimeng.jianying.com/ai-tool/home/?type=image&workspace=0
  // job.prompt: 完整提示词
  // job.assets: 三张参考图 [人物, 服装, 场景]
  // job.styleImageId, job.sceneId: 用于结果关联
}
```

流程：
1. 等待页面加载完成（检测 `#root` 或特定元素出现）
2. 点击底部"图片生成"Tab
3. 选择模型（文字"图片5.0 Lite 9:16 2K"）
4. 上传三张参考图（三组 upload 区域，各不同 label）
5. 填入 prompt
6. 点击生成按钮
7. 轮询检测生成结果（检测 `.result-item img` 或类似元素，8s 稳定性）
8. 收集所有结果图片（最多4张）
9. 调用 `serializeImages` + `postJson(..., /result)` 上报
10. 错误处理和进度记录与 GPT handler 一致

关键 DOM 元素需要通过实际测试确认，此处先写框架，DOM 选择器待验证后更新。

Run: N/A

- [ ] **Step 2: 实现页面加载和 Tab 切换逻辑**

```javascript
async function waitForPageReady() {
  await waitFor(() => document.querySelector("#root > div"), { timeoutMs: 30000, label: "jimeng page ready" });
}

async function clickImageTab() {
  // 查找底部 Tab：文字包含"图片生成"或类似
  const tabs = await waitFor(() => {
    return Array.from(document.querySelectorAll("div[role='tab'], button")).filter(el =>
      el.innerText.includes("图片")
    );
  }, { timeoutMs: 10000 });

  if (tabs.length > 0) {
    tabs[0].click();
    await delay(500);
  }
}

async function selectModel() {
  // 查找模型选择器：文字"图片5.0 Lite 9:16 2K"
  const modelOption = await waitFor(() => {
    return Array.from(document.querySelectorAll("div, span, button")).find(el =>
      el.innerText.includes("图片5.0 Lite")
    );
  }, { timeoutMs: 10000 });

  if (modelOption) {
    modelOption.click();
    await delay(300);
  }
}
```

- [ ] **Step 3: 实现图片上传逻辑**

即梦的图片上传与 GPT 不同——不是单个 textarea，而是三组独立的 upload 区域。参考图从 `job.assets` 获取，通过 label 区分"人物"、"服装"、"场景"。

```javascript
async function uploadReferenceImages(assets) {
  // 资产映射：label -> url
  const assetMap = {};
  for (const asset of assets) {
    assetMap[asset.label] = asset.url;
  }

  // 找到三个上传区域（按顺序：人物、服装、场景）
  const uploadSlots = await waitFor(() => {
    return Array.from(document.querySelectorAll("[data-testid*='upload'], .upload-slot, [class*='upload']")).filter(isVisible);
  }, { timeoutMs: 15000, label: "upload slots" });

  const labels = ["人物", "服装", "场景"];
  for (let i = 0; i < Math.min(uploadSlots.length, 3); i++) {
    const label = labels[i];
    const asset = Object.values(assetMap)[i]; // 按顺序取
    if (!asset) continue;

    // 点击上传区域触发文件选择
    uploadSlots[i].click();
    await delay(500);

    // 获取文件输入框
    const fileInput = await waitFor(() => document.querySelector("input[type='file']"), { timeoutMs: 5000 });
    const file = await fetchAssetAsFile({ url: asset.url, name: `${label}.jpg` });

    const transfer = new DataTransfer();
    transfer.items.add(file);
    fileInput.files = transfer.files;
    fileInput.dispatchEvent(new Event("change", { bubbles: true }));

    await waitForUploadComplete();
  }
}
```

- [ ] **Step 4: 实现 prompt 填写和生成按钮点击**

```javascript
async function fillPrompt(promptText) {
  // 查找 prompt 输入框（contenteditable 或 textarea）
  const promptBox = await waitFor(() => {
    return document.querySelector("div[contenteditable='true'][role='textbox'], textarea");
  }, { timeoutMs: 10000 });

  if (promptBox) {
    clearAndFill(promptBox, promptText);
  }
}

async function clickGenerateButton() {
  // 查找生成按钮：文字"生成"或"开始生成"
  const generateBtn = await waitFor(() => {
    return Array.from(document.querySelectorAll("button")).find(el =>
      el.innerText.includes("生成")
    );
  }, { timeoutMs: 10000, label: "generate button" });

  if (generateBtn && !generateBtn.disabled) {
    generateBtn.click();
  }
}
```

- [ ] **Step 5: 实现结果轮询和序列化**

```javascript
async function waitForGeneratedImages(timeoutMs) {
  const deadline = Date.now() + (timeoutMs || DEFAULT_TIMEOUT_MS);
  let stableSince = 0;
  let lastKeys = [];

  while (Date.now() < deadline) {
    // 查找结果区域中的图片
    const resultImages = Array.from(document.querySelectorAll(".result-item img, [class*='result'] img")).filter(isVisible);

    const currentKeys = resultImages.map(img => img.src || img.currentSrc).filter(Boolean);

    if (currentKeys.length > 0) {
      const sameAsPrevious = currentKeys.length === lastKeys.length &&
        currentKeys.every((key, idx) => key === lastKeys[idx]);

      if (sameAsPrevious) {
        if (!stableSince) stableSince = Date.now();
        if (Date.now() - stableSince > 8000) {
          return resultImages;
        }
      } else {
        stableSince = Date.now();
        lastKeys = currentKeys;
      }
    }

    await delay(2000);
  }

  throw new Error("Timed out while waiting for generated images on Jimeng");
}
```

- [ ] **Step 6: 提交**

```bash
git add extension/content-handlers/jimeng-image.js
git commit -m "feat: add Jimeng image generation handler"
```

---

## Task 3: 创建即梦视频 handler（jimeng-video.js）

**Files:**
- Create: `extension/content-handlers/jimeng-video.js`

- [ ] **Step 1: 编写 `jimeng-video.js` 基础框架**

大部分逻辑与 `jimeng-image.js` 类似，主要差异：
- 选择"视频生成"Tab（而非图片生成）
- 选择"Seedance1.0 首尾帧"模型
- 只上传一张首帧图
- 额外填写动作描述字段
- 等待视频元素（而非图片元素）

```javascript
// extension/content-handlers/jimeng-video.js

const DEFAULT_TIMEOUT_MS = 15 * 60 * 1000;

async function runJimengVideoJob(job, serverUrl) {
  // job.platform === "jimeng" (video mode)
  // job.targetUrl: https://jimeng.jianying.com/ai-tool/home/?type=video&workspace=0
  // job.assets: [首帧图]
  // job.movement 或 job.movementId: 动作描述
  // job.prompt: 提示词
}
```

- [ ] **Step 2: 实现 Tab 切换和模型选择**

```javascript
async function clickVideoTab() {
  const tabs = await waitFor(() => {
    return Array.from(document.querySelectorAll("div[role='tab'], button")).filter(el =>
      el.innerText.includes("视频")
    );
  }, { timeoutMs: 10000 });

  if (tabs.length > 0) {
    // 可能第一个是图片，第二个是视频
    const videoTab = tabs.find(tab => tab.innerText.includes("视频")) || tabs[tabs.length - 1];
    videoTab.click();
    await delay(500);
  }
}

async function selectVideoModel() {
  // "Seedance1.0 首尾帧"
  const modelOption = await waitFor(() => {
    return Array.from(document.querySelectorAll("div, span, button")).find(el =>
      el.innerText.includes("Seedance")
    );
  }, { timeoutMs: 10000 });

  if (modelOption) {
    modelOption.click();
    await delay(300);
  }
}
```

- [ ] **Step 3: 实现首帧图上传和动作描述填写**

```javascript
async function uploadFirstFrame(asset) {
  const file = await fetchAssetAsFile(asset);

  // 查找首帧图上传区域
  const uploadArea = await waitFor(() => {
    return Array.from(document.querySelectorAll("[class*='first-frame'], [class*='cover'], [data-testid*='upload']")).find(isVisible);
  }, { timeoutMs: 10000, label: "first frame upload area" });

  uploadArea.click();
  await delay(500);

  const fileInput = await waitFor(() => document.querySelector("input[type='file']"), { timeoutMs: 5000 });
  const transfer = new DataTransfer();
  transfer.items.add(file);
  fileInput.files = transfer.files;
  fileInput.dispatchEvent(new Event("change", { bubbles: true }));

  await delay(1000);
}

async function fillMovement(movementText) {
  // 查找动作描述输入框
  const input = await waitFor(() => {
    return document.querySelector("input[placeholder*='动作'], textarea[placeholder*='动作']");
  }, { timeoutMs: 10000 });

  if (input) {
    input.focus();
    input.value = movementText;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }
}
```

- [ ] **Step 4: 实现视频结果轮询**

```javascript
async function waitForGeneratedVideo(timeoutMs) {
  const deadline = Date.now() + (timeoutMs || DEFAULT_TIMEOUT_MS);
  let stableSince = 0;
  let lastSrc = "";

  while (Date.now() < deadline) {
    // 查找视频元素或下载链接
    const videoEl = document.querySelector("video");
    const downloadLink = Array.from(document.querySelectorAll("a[href*='download'], button")).find(el =>
      el.innerText.includes("下载") || el.getAttribute("href")?.includes(".mp4")
    );

    if (videoEl && videoEl.src) {
      const currentSrc = videoEl.src;
      if (currentSrc === lastSrc && lastSrc) {
        if (!stableSince) stableSince = Date.now();
        if (Date.now() - stableSince > 8000) {
          return videoEl;
        }
      } else {
        stableSince = Date.now();
        lastSrc = currentSrc;
      }
    }

    if (downloadLink) {
      return { src: downloadLink.href || downloadLink.getAttribute("data-src") };
    }

    await delay(2000);
  }

  throw new Error("Timed out while waiting for generated video on Jimeng");
}
```

- [ ] **Step 5: 提交**

```bash
git add extension/content-handlers/jimeng-video.js
git commit -m "feat: add Jimeng video generation handler"
```

---

## Task 4: 修改 Background Script（支持 platform 路由和 cancelAll）

**Files:**
- Modify: `extension/background.js:20-80`（`startController`、`runJobInFreshTab` 函数）

- [ ] **Step 1: 修改 `startController` 传递 platform 参数给 content script**

找到 `chrome.tabs.sendMessage(tabId, { type: "controller:runSingleJob", serverUrl, job })` 附近，job 对象中已包含 `targetUrl` 和 `platform`，content script 会读取。

实际代码可能不需要大改，因为 job 对象本身就包含这些字段。但需要确认 `targetUrl` 被正确用于打开标签页。

- [ ] **Step 2: 修改 `openFreshChatWindow` 使用 `job.targetUrl` 而非 hardcode**

```javascript
// 原有
function chatStartUrl() {
  return "https://chatgpt.com/images";
}

// 改为
async function openJobTab(job) {
  const targetUrl = job.targetUrl || chatStartUrl();
  const createdWindow = await chrome.windows.create({
    url: targetUrl,
    type: "normal",
    focused: true,
  });
  const tab = createdWindow.tabs?.[0];
  if (!createdWindow.id || !tab?.id) {
    throw new Error("Failed to create window");
  }
  await waitForTabComplete(tab.id);
  await ensureContentScript(tab.id);
  return { tabId: tab.id, windowId: createdWindow.id };
}
```

- [ ] **Step 3: 在 `runJobInFreshTab` 中使用 `openJobTab(job)`**

将 `openFreshChatWindow()` 调用替换为 `openJobTab(payload.job)`。

- [ ] **Step 4: 添加 `cancelAll` 消息处理**

在 background.js 的 `chrome.runtime.onMessage.addListener` 中添加：

```javascript
if (message?.type === "popup:cancelAll") {
  // 调用 local_bridge 的 cancel all 接口，带 platform 过滤
  const { platform } = message;
  try {
    const resp = await fetch(`${controllerState.serverUrl}/v1/jobs/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ platform }),
    });
    const result = await resp.json();
    sendResponse({ ok: true, result });
  } catch (error) {
    sendResponse({ ok: false, error: String(error) });
  }
  return true;
}
```

- [ ] **Step 5: 修改 `startController` 接收 platform 参数**

将 `message.serverUrl` 改为 `message.serverUrl` + `message.platform`，但实际上 Start 是全局的，不需要按平台启动。Cancel All 是按平台的。platform 参数只在 cancelAll 时使用。

- [ ] **Step 6: 提交**

```bash
git add extension/background.js
git commit -m "feat: support targetUrl-based tab opening and cancelAll"
```

---

## Task 5: 重写 Popup UI（按平台分组）

**Files:**
- Rewrite: `extension/popup.html`
- Rewrite: `extension/popup.js`

- [ ] **Step 1: 重写 `popup.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Media Image Runner</title>
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }
      body {
        width: 360px;
        padding: 12px;
        font-family: "Segoe UI", sans-serif;
        background: #f5f1e8;
        color: #1f1d1a;
        font-size: 13px;
      }
      .platform-section {
        border: 1px solid #e6dac7;
        border-radius: 10px;
        background: white;
        margin-bottom: 10px;
        overflow: hidden;
      }
      .platform-header {
        padding: 10px 14px;
        background: #faf6ee;
        border-bottom: 1px solid #e6dac7;
        font-weight: 600;
        font-size: 14px;
      }
      .platform-body { padding: 10px 14px; }
      .actions { display: flex; gap: 6px; margin-bottom: 8px; }
      button {
        padding: 6px 14px;
        border: 0;
        border-radius: 999px;
        background: #1f1d1a;
        color: white;
        cursor: pointer;
        font-size: 12px;
      }
      button.secondary { background: #8e6d3f; }
      button.danger { background: #9a1c1c; }
      button:disabled { opacity: 0.5; cursor: not-allowed; }
      .stats {
        display: flex;
        gap: 12px;
        margin-bottom: 6px;
        font-size: 11px;
        color: #666;
      }
      .stat-item { display: flex; gap: 4px; }
      .stat-label { color: #999; }
      .status-line {
        font-size: 11px;
        color: #555;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .error-line { color: #9a1c1c; font-size: 11px; margin-top: 2px; }
    </style>
  </head>
  <body>
    <div id="platforms"></div>
    <script src="popup.js"></script>
  </body>
</html>
```

- [ ] **Step 2: 重写 `popup.js`**

```javascript
const PLATFORMS = [
  { id: "gpt", name: "ChatGPT 图片", matches: ["chatgpt.com", "openai.com"] },
  { id: "jimeng", name: "即梦图片", matches: ["jimeng.jianying.com"] },
  { id: "jimeng", name: "即梦视频", matches: ["jimeng.jianying.com"] },
];

const controllerState = {};

function renderPlatformSection(platform) {
  const state = controllerState[platform.id] || { running: false, busy: false, lastMessage: "Idle", currentJobId: null, lastError: null };

  return `
    <div class="platform-section" data-platform="${platform.id}">
      <div class="platform-header">${platform.name}</div>
      <div class="platform-body">
        <div class="actions">
          <button class="start-btn" data-platform="${platform.id}" ${state.running ? 'disabled' : ''}>Start</button>
          <button class="stop-btn" data-platform="${platform.id}" ${!state.running ? 'disabled' : ''}>Stop</button>
          <button class="cancel-all-btn" data-platform="${platform.id}">Cancel All</button>
        </div>
        <div class="stats">
          <span class="stat-item"><span class="stat-label">Job:</span><span class="job-id">${state.currentJobId || "-"}</span></span>
          <span class="stat-item"><span class="stat-label">Status:</span><span class="status">${state.lastMessage || "Idle"}</span></span>
        </div>
        ${state.lastError ? `<div class="error-line">${state.lastError}</div>` : ""}
      </div>
    </div>
  `;
}

function render() {
  const container = document.getElementById("platforms");
  container.innerHTML = PLATFORMS.map(renderPlatformSection).join("");

  // 绑定事件
  container.querySelectorAll(".start-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const platform = btn.dataset.platform;
      chrome.runtime.sendMessage({ type: "popup:start", platform, serverUrl: getServerUrl() });
    });
  });

  container.querySelectorAll(".stop-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const platform = btn.dataset.platform;
      chrome.runtime.sendMessage({ type: "popup:stop", platform });
    });
  });

  container.querySelectorAll(".cancel-all-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const platform = btn.dataset.platform;
      chrome.runtime.sendMessage({ type: "popup:cancelAll", platform });
    });
  });
}

function getServerUrl() {
  return document.getElementById("serverUrl")?.value || "http://127.0.0.1:8765";
}

async function refresh() {
  const response = await chrome.runtime.sendMessage({ type: "popup:getState" });
  if (response.state) {
    // response.state 格式: { gpt: {...}, jimeng: {...} }
    Object.assign(controllerState, response.state);
  }
  render();
}

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "controllerState") {
    // 各平台的 state 可能在一起或单独发过来
    if (message.state.platform) {
      controllerState[message.state.platform] = message.state;
    } else {
      Object.assign(controllerState, message.state);
    }
    render();
  }
});

refresh();
```

- [ ] **Step 3: 提交**

```bash
git add extension/popup.html extension/popup.js
git commit -m "feat: rewrite popup with per-platform controls"
```

---

## Task 6: 更新 manifest.json（添加即梦权限）

**Files:**
- Modify: `extension/manifest.json`

- [ ] **Step 1: 更新 host_permissions 和 content_scripts matches**

```json
{
  "host_permissions": [
    "https://chatgpt.com/*",
    "https://chat.openai.com/*",
    "https://*.openai.com/*",
    "https://*.oaiusercontent.com/*",
    "https://*.blob.core.windows.net/*",
    "https://jimeng.jianying.com/*",
    "http://127.0.0.1:8765/*",
    "http://localhost:8765/*"
  ],
  "content_scripts": [
    {
      "matches": [
        "https://chatgpt.com/*",
        "https://chat.openai.com/*",
        "https://jimeng.jianying.com/*"
      ],
      "js": ["content-script.js"],
      "run_at": "document_idle"
    }
  ]
}
```

- [ ] **Step 2: 提交**

```bash
git add extension/manifest.json
git commit -m "feat: add Jimeng host permissions and content script matches"
```

---

## Task 7: local_bridge server.py 修改（Job.to_public_dict 增加 platform/targetUrl）

**Files:**
- Modify: `local_bridge/server.py`（`Job.to_public_dict` 方法，约第 155-171 行）

- [ ] **Step 1: 查看 `to_public_dict` 当前实现**

```python
def to_public_dict(self, base_url: str) -> dict[str, Any]:
    return {
        "id": self.id,
        "caseFile": str(self.case_file),
        "prompt": self.prompt,
        "assets": [
            {
                "index": index,
                "label": asset["label"],
                "name": asset["name"],
                "mimeType": asset["mimeType"],
                "url": f"{base_url}/v1/assets/{self.id}/{index}",
            }
            for index, asset in enumerate(self.assets)
        ],
        "timeoutSeconds": 900,
    }
```

- [ ] **Step 2: 添加 `platform` 和 `targetUrl` 字段**

根据 job 的来源（GPT 还是即梦）返回不同字段。即梦 job 在生成时已设置 `platform` 和 `targetUrl` 在 job 对象的额外字段中。

```python
def to_public_dict(self, base_url: str) -> dict[str, Any]:
    result = {
        "id": self.id,
        "caseFile": str(self.case_file),
        "prompt": self.prompt,
        "assets": [
            {
                "index": index,
                "label": asset["label"],
                "name": asset["name"],
                "mimeType": asset["mimeType"],
                "url": f"{base_url}/v1/assets/{self.id}/{index}",
            }
            for index, asset in enumerate(self.assets)
        ],
        "timeoutSeconds": 900,
    }
    # platform 和 targetUrl 由 Job 的额外属性提供
    if hasattr(self, "platform") and self.platform:
        result["platform"] = self.platform
    if hasattr(self, "target_url") and self.target_url:
        result["targetUrl"] = self.target_url
    return result
```

- [ ] **Step 3: 提交**

```bash
git add local_bridge/server.py
git commit -m "feat: add platform and targetUrl to Job.to_public_dict()"
```

---

## Task 8: 整体集成测试

- [ ] **Step 1: 验证文件结构**

```
extension/
  manifest.json
  background.js
  popup.html
  popup.js
  content-script.js
  content-handlers/
    gpt.js
    jimeng-image.js
    jimeng-video.js
```

- [ ] **Step 2: 检查 import/require 路径**

`content-script.js` 使用 `require("./content-handlers/gpt.js")` 引用 handler。Chrome Extension MV3 不支持 `require()`（service worker 使用 ES module 或全局命名空间）。需要改为动态 import 或将所有 handler 代码内联到一个文件。

**解决方案：使用 ES module import**

在 `content-script.js` 顶部：
```javascript
import { runGptJob } from "./content-handlers/gpt.js";
import { runJimengImageJob } from "./content-handlers/jimeng-image.js";
import { runJimengVideoJob } from "./content-handlers/jimeng-video.js";
```

manifest.json 中 content-script.js 保持 `"type": "module"` 或在 script tag 上添加 `type="module"`。

- [ ] **Step 3: 最终提交**

```bash
git add -A
git commit -m "feat: browser extension multi-platform support"
```

---

## 依赖关系

1. Task 1 → Task 2, Task 3（GPT handler 是模板）
2. Task 1, 2, 3 → Task 5（popup 需要 platform 列表匹配 handler）
3. Task 4, 6 → Task 8（background + manifest 是集成前提）

---

## 验证方式

- 在 Chrome 中加载 `extension/` 目录作为 unpacked extension
- 打开 ChatGPT 页面，测试 Start/Stop 能正常控制 GPT job
- 打开即梦页面，验证 content script 正确加载
- 查看 Popup 上三个平台独立显示
- **注意**：实际 DOM 选择器需要根据真实页面调整，本计划中的选择器为合理推测，需在实际页面上验证后更新