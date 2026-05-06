# Jimeng Video Browser Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 jimeng 视频（首尾帧模式）的浏览器自动化，从上传首帧图片到下载视频到上报结果到 local_bridge 的完整流程。

**Architecture:** 在 `extension/jimeng-steps.js` 中新增 video 专用的 step 函数（S1V-S8V），在 `extension/content-script.js` 中新增 `runJimengVideoJobHandler` 调用这些 steps。结果通过 bridgeFetch → local_bridge 的 `/v1/job/{id}/result` 上报，视频文件通过 `/api/videos` 上传。

**Tech Stack:** Chrome Extension + local_bridge + Media AI API

---

## File Structure

| 文件 | 职责 |
|------|------|
| `extension/jimeng-steps.js` | 新增 8 个 step 函数（video 专用），复用水 imagestep 的工具函数 |
| `extension/content-script.js` | 新增 `runJimengVideoJobHandler`，修改 `runJob` 支持 jimeng video |
| `local_bridge/single_task.py` | 确认 video job 的 kind→platform 映射 |
| `local_bridge/server.py` | 确认 video result 上传端点和逻辑 |

---

## Task 1: 添加 jimeng-steps.js 的 video step 函数

**Files:**
- Modify: `extension/jimeng-steps.js`（在 IIFE 末尾 `})();` 前新增 8 个函数，并更新 `window.` 导出列表）

- [ ] **Step 1: 在 jimeng-steps.js 新增 stepVideoNav**

```javascript
// Step V1: Navigate to jimeng video page
async function stepVideoNav(targetUrl) {
  if (window.location.href !== targetUrl) {
    window.location.href = targetUrl;
    return { ok: false, data: { status: "navigating" }, error: null };
  }
  return { ok: true, data: { status: "already_on_page", url: window.location.href }, error: null };
}
```

- [ ] **Step 2: 新增 stepVideoTab（确认视频生成 tab 已选中）**

```javascript
// Step V2: Confirm "视频生成" tab (video page defaults to this, just verify)
async function stepVideoTab() {
  // Video page URL contains type=video — wait for that confirmation
  if (window.location.href.includes("type=video")) {
    try {
      waitFor(() => document.querySelector('[role="combobox"]'), { timeoutMs: 15000, label: "combobox" });
      return { ok: true, data: { status: "already_on_video_tab" }, error: null };
    } catch {
      return { ok: false, data: null, error: "type=video page loaded but combobox not found" };
    }
  }
  // Fallback: click "视频生成" tab if URL doesn't have type=video
  const candidates = () => Array.from(document.querySelectorAll("*")).filter(el =>
    el.childNodes.length === 1 && textLike(el.textContent, "视频生成")
  );
  let tab = null;
  const tabs = candidates();
  for (const t of tabs) { if (isVisible(t)) { tab = t; break; } }
  if (!tab) return { ok: false, data: null, error: "视频生成 tab not found" };
  tab.click();
  await delay(1000);
  waitFor(() => window.location.href.includes("type=video"), { timeoutMs: 15000, label: "type=video URL" });
  return { ok: true, data: { status: "clicked_video_tab" }, error: null };
}
```

- [ ] **Step 3: 新增 stepVideoModel（选择 Seedance 1.0 首尾帧）**

```javascript
// Step V3: Select Seedance 1.0 model + 首尾帧 mode
async function stepVideoModel() {
  const delayMs = 500;
  // Wait for model combobox (Seedance 1.0 text)
  waitFor(() => {
    const cb = Array.from(document.querySelectorAll('[role="combobox"]')).find(el =>
      el.textContent.includes("Seedance") || el.textContent.includes("视频生成")
    );
    return cb || null;
  }, { timeoutMs: 20000, label: "video_model_combobox" });

  // Click the model combobox (Seedance 1.0)
  const modelCb = Array.from(document.querySelectorAll('[role="combobox"]')).find(el =>
    el.textContent.includes("Seedance") && !el.textContent.includes("首尾帧")
  );
  if (!modelCb) {
    // Already on correct model, skip
    return { ok: true, data: { status: "model_already_selected" }, error: null };
  }
  modelCb.click();
  await delay(delayMs);

  // Find listbox with Seedance option
  const listbox = Array.from(document.querySelectorAll('[role="listbox"]')).find(lb =>
    lb.textContent.includes("Seedance")
  );
  if (!listbox) {
    // Model dropdown may not be open, try clicking body to close and verify
    document.body.click();
    await delay(300);
    return { ok: true, data: { status: "model_select_skipped" }, error: null };
  }

  const options = Array.from(listbox.querySelectorAll('[role="option"]'));
  const seedanceOption = options.find(o => o.textContent.includes("Seedance"));
  if (seedanceOption) {
    seedanceOption.click();
    await delay(delayMs);
  }
  document.body.click();
  await delay(300);

  // Verify model combobox text
  const modelText = modelCb?.textContent?.trim() || "";
  return { ok: true, data: { modelText }, error: null };
}
```

- [ ] **Step 4: 新增 stepVideoRatio（选择比例，可选）**

```javascript
// Step V4: Select video aspect ratio (e.g. 16:9, 9:16, 1:1)
// If no ratio is specified in job, uses the default (16:9)
async function stepVideoRatio(job) {
  const targetRatio = job.aspectRatio || "16:9"; // default
  if (targetRatio === "16:9") {
    // Default ratio, no action needed
    return { ok: true, data: { ratio: "16:9", status: "default" }, error: null };
  }

  // Click ratio button to open dropdown
  const ratioBtn = Array.from(document.querySelectorAll("button")).find(el => {
    const text = el.textContent.trim();
    return /\d+:\d+/.test(text) && isVisible(el);
  });
  if (!ratioBtn) return { ok: false, data: null, error: "Ratio button not found" };

  ratioBtn.click();
  await delay(300);

  // Find lv-radio labels in dropdown
  const ratioLabel = Array.from(document.querySelectorAll("label.lv-radio")).find(el =>
    el.textContent.trim() === targetRatio
  );
  if (!ratioLabel) {
    document.body.click();
    await delay(200);
    return { ok: false, data: null, error: `Ratio ${targetRatio} not found in dropdown` };
  }
  ratioLabel.click();
  await delay(200);
  document.body.click();
  await delay(300);

  // Verify
  const ratioBtnAfter = Array.from(document.querySelectorAll("button")).find(el =>
    /\d+:\d+/.test(el.textContent || "")
  );
  const ratioText = ratioBtnAfter?.textContent?.trim() || "";
  return { ok: true, data: { ratio: ratioText, resolution: "default" }, error: null };
}
```

- [ ] **Step 5: 新增 stepVideoUploadFirstFrame**

```javascript
// Step V5: Upload first frame image
// Handles the reference-upload-Yi4KkS div with hidden file input inside
async function stepVideoUploadFirstFrame(asset) {
  const delayMs = 500;

  // Find first-frame upload zone (look for div with class reference-upload-*)
  // and text "首帧" nearby
  const uploadZones = Array.from(document.querySelectorAll("[class*='reference-upload-']")).filter(el => {
    return isVisible(el) && (el.textContent.includes("首帧") || el.querySelector("svg"));
  });

  let targetZone = null;
  for (const zone of uploadZones) {
    // Find the parent that contains "首帧" text
    const parentText = zone.closest("[class*='reference-item']")?.textContent || "";
    if (parentText.includes("首帧")) {
      targetZone = zone;
      break;
    }
  }
  if (!targetZone) {
    // Fallback: find first visible upload zone
    targetZone = uploadZones[0];
  }
  if (!targetZone) throw new Error("First frame upload zone not found");

  // Get the hidden file input inside this zone
  const hiddenInput = targetZone.querySelector("input[type='file]");
  if (!hiddenInput) throw new Error("Hidden file input not found in first frame upload zone");

  // Fetch asset as File (using bridgeFetch + blobBase64)
  const response = await bridgeFetch({ url: asset.url, responseType: "blobBase64" });
  const binary = atob(response.base64Data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const mimeType = asset.mimeType || response.mimeType || "image/png";
  const file = new File([bytes], asset.name, { type: mimeType });

  // Create DataTransfer and set files
  const dataTransfer = new DataTransfer();
  dataTransfer.items.add(file);
  hiddenInput.files = dataTransfer.files;
  hiddenInput.dispatchEvent(new Event("change", { bubbles: true }));

  // Wait for preview image to appear (img with width > 50, not data:/blob:)
  await waitFor(() => {
    const previewImgs = Array.from(targetZone.querySelectorAll("img")).filter(img => {
      if (!img.src || img.src.startsWith("data:") || img.src.startsWith("blob:")) return false;
      try { return img.getBoundingClientRect().width > 50; } catch { return false; }
    });
    return previewImgs.length > 0 ? previewImgs[0] : null;
  }, { timeoutMs: 15000, label: "first_frame_preview" });

  return { ok: true, data: { uploaded: asset.name }, error: null };
}
```

- [ ] **Step 6: 新增 stepVideoUploadLastFrame（可选，如 job.assets 有尾帧）**

```javascript
// Step V6: Upload last frame image (optional, only if asset with label "lastFrame" or second asset exists)
async function stepVideoUploadLastFrame(asset) {
  const delayMs = 500;

  // Find last-frame upload zone
  const uploadZones = Array.from(document.querySelectorAll("[class*='reference-upload-']")).filter(el => {
    return isVisible(el);
  });

  let targetZone = null;
  for (const zone of uploadZones) {
    const parentText = zone.closest("[class*='reference-item']")?.textContent || "";
    if (parentText.includes("尾帧")) {
      targetZone = zone;
      break;
    }
  }

  if (!targetZone) {
    // No last frame upload zone found — this is optional, return ok with skip
    return { ok: true, data: { status: "skipped", reason: "no_last_frame_zone" }, error: null };
  }

  const hiddenInput = targetZone.querySelector("input[type='file']");
  if (!hiddenInput) {
    return { ok: true, data: { status: "skipped", reason: "no_file_input" }, error: null };
  }

  const response = await bridgeFetch({ url: asset.url, responseType: "blobBase64" });
  const binary = atob(response.base64Data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const mimeType = asset.mimeType || response.mimeType || "image/png";
  const file = new File([bytes], asset.name, { type: mimeType });

  const dataTransfer = new DataTransfer();
  dataTransfer.items.add(file);
  hiddenInput.files = dataTransfer.files;
  hiddenInput.dispatchEvent(new Event("change", { bubbles: true }));

  await waitFor(() => {
    const previewImgs = Array.from(targetZone.querySelectorAll("img")).filter(img => {
      if (!img.src || img.src.startsWith("data:") || img.src.startsWith("blob:")) return false;
      try { return img.getBoundingClientRect().width > 50; } catch { return false; }
    });
    return previewImgs.length > 0 ? previewImgs[0] : null;
  }, { timeoutMs: 15000, label: "last_frame_preview" });

  return { ok: true, data: { uploaded: asset.name }, error: null };
}
```

- [ ] **Step 7: 新增 stepVideoPrompt（填写运动描述和创意描述）**

```javascript
// Step V7: Fill movement description and prompt text
async function stepVideoPrompt(job) {
  const delayMs = 300;

  // Find the two textareas on the video page
  // They have the same placeholder text, distinguish by position or order
  const textareas = Array.from(document.querySelectorAll("textarea")).filter(el =>
    isVisible(el) && el.placeholder.includes("运动方式")
  );

  if (textareas.length < 1) {
    // Try generic textarea approach
    const allTextareas = Array.from(document.querySelectorAll("textarea")).filter(isVisible);
    if (allTextareas.length < 1) throw new Error("No textarea found for movement/prompt input");
    const t = allTextareas[0];
    t.focus();
    t.value = job.movement || job.prompt || "";
    t.dispatchEvent(new InputEvent("input", { bubbles: true, data: job.prompt || "" }));
    t.dispatchEvent(new Event("change", { bubbles: true }));
    await delay(delayMs);
    return { ok: true, data: { promptLength: (job.prompt || "").length }, error: null };
  }

  // First textarea = movement description (运动描述)
  const movementText = job.movement || job.mrompt || "";
  const movementTa = textareas[0];
  movementTa.focus();
  movementTa.value = "";
  movementTa.value = movementText;
  movementTa.dispatchEvent(new InputEvent("input", { bubbles: true, data: movementText }));
  movementTa.dispatchEvent(new Event("change", { bubbles: true }));
  await delay(delayMs);

  // Second textarea = creative description (prompt)
  const promptText = job.prompt || "";
  if (textareas.length > 1) {
    const promptTa = textareas[1];
    promptTa.focus();
    promptTa.value = "";
    promptTa.value = promptText;
    promptTa.dispatchEvent(new InputEvent("input", { bubbles: true, data: promptText }));
    promptTa.dispatchEvent(new Event("change", { bubbles: true }));
    await delay(delayMs);
  }

  return { ok: true, data: { movementLength: movementText.length, promptLength: promptText.length }, error: null };
}
```

- [ ] **Step 8: 新增 stepVideoGenerate（点击生成按钮）**

```javascript
// Step V8: Click generate button and wait for processing to start
async function stepVideoGenerate() {
  const delayMs = 200;

  // Wait for submit button to be enabled
  const enabledSubmit = waitFor(() => {
    // Primary button that is not disabled
    const btns = Array.from(document.querySelectorAll("button.lv-btn-primary"));
    const enabled = btns.find(b => !b.disabled && b.textContent.trim() === "");
    return enabled || null;
  }, { timeoutMs: 30000, label: "enabled_video_submit_button" });

  const targetBtn = await enabledSubmit;
  if (!targetBtn) {
    // Try alternate selector: any enabled primary button
    const altBtn = Array.from(document.querySelectorAll("button")).find(el =>
      isVisible(el) && !el.disabled && el.className.includes("primary")
    );
    if (!altBtn) {
      const allBtns = Array.from(document.querySelectorAll("button")).slice(0, 8).map(b =>
        `dis:${b.disabled} cls:${b.className.replace(/\S+/g, m => m).slice(0, 35)}`
      ).join(" | ");
      throw new Error(`Video generate button never became enabled (all_btns: ${allBtns})`);
    }
    altBtn.click();
    await delay(delayMs);
    const isProcessing = Array.from(document.querySelectorAll("button.primary")).some(b => b.disabled);
    return { ok: true, data: { clicked: "alt", processing: isProcessing }, error: null };
  }

  targetBtn.click();
  await delay(delayMs);

  const isProcessing = targetBtn.disabled;
  console.log("[stepVideoGenerate] clicked, processing:", isProcessing);
  return { ok: true, data: { clicked: "primary", processing: isProcessing }, error: null };
}
```

- [ ] **Step 9: 新增 stepVideoWait（等待视频生成并提取下载 URL）**

```javascript
// Step V9: Wait for generated video, return video URL
// Timeout: 10 minutes (600s)
// Strategy: wait for video element src stable OR download link stable for 8s
async function stepVideoWait(job) {
  const TIMEOUT_MS = (job.timeoutSeconds ? job.timeoutSeconds : 600) * 1000;
  const deadline = Date.now() + TIMEOUT_MS;
  const POLL_INTERVAL_MS = 3000;
  const STABLE_DURATION_MS = 8000;

  // Wait for /generate navigation first (jimeng transitions here after clicking generate)
  if (!window.location.href.includes("/generate")) {
    console.log("[stepVideoWait] waiting for /generate navigation...");
    const navDeadline = Date.now() + 60000;
    while (Date.now() < navDeadline) {
      if (window.location.href.includes("/generate")) {
        console.log("[stepVideoWait] navigated to:", window.location.href);
        break;
      }
      await delay(500);
    }
  }

  console.log("[stepVideoWait] START, deadline in", Math.round((deadline - Date.now()) / 1000), "s at:", window.location.href);

  let lastVideoSrc = "";
  let lastDownloadHref = "";
  let videoStableSince = 0;
  let downloadStableSince = 0;

  while (Date.now() < deadline) {
    await delay(POLL_INTERVAL_MS);

    // Check video element
    const videoEl = document.querySelector("video");
    if (videoEl && isVisible(videoEl) && videoEl.src && !videoEl.src.startsWith("data:") && !videoEl.src.startsWith("blob:")) {
      const currentSrc = videoEl.src;
      if (currentSrc !== lastVideoSrc) {
        lastVideoSrc = currentSrc;
        videoStableSince = Date.now();
        console.log("[stepVideoWait] video src changed:", currentSrc.slice(0, 60));
      } else if (Date.now() - videoStableSince > STABLE_DURATION_MS) {
        console.log("[stepVideoWait] video stable for", STABLE_DURATION_MS, "ms:", currentSrc.slice(0, 60));
        return { ok: true, data: { videoUrl: currentSrc, sourceType: "videoElement" }, error: null };
      }
    }

    // Check download link
    const downloadLinks = Array.from(document.querySelectorAll("a[href]")).filter(a =>
      (a.href.includes(".mp4") || a.href.includes(".webm")) && isVisible(a)
    );
    if (downloadLinks.length > 0) {
      const dl = downloadLinks[0];
      const currentHref = dl.href;
      if (currentHref !== lastDownloadHref) {
        lastDownloadHref = currentHref;
        downloadStableSince = Date.now();
        console.log("[stepVideoWait] download link changed:", currentHref.slice(0, 60));
      } else if (Date.now() - downloadStableSince > STABLE_DURATION_MS) {
        console.log("[stepVideoWait] download link stable for", STABLE_DURATION_MS, "ms:", currentHref.slice(0, 60));
        return { ok: true, data: { videoUrl: currentHref, sourceType: "downloadLink" }, error: null };
      }
    }

    // Check for "去查看" button (generated video card ready to view)
    const viewBtns = Array.from(document.querySelectorAll("button")).filter(el =>
      el.textContent.includes("去查看") && isVisible(el)
    );
    if (viewBtns.length > 0) {
      console.log("[stepVideoWait] found 去查看 button, clicking...");
      viewBtns[0].click();
      await delay(2000);
      // After clicking, check for video element again
      const newVideoEl = document.querySelector("video");
      if (newVideoEl && newVideoEl.src && !newVideoEl.src.startsWith("data:")) {
        lastVideoSrc = newVideoEl.src;
        videoStableSince = Date.now();
      }
    }
  }

  return { ok: false, data: null, error: `Timed out after 10min, no video found` };
}
```

- [ ] **Step 10: 更新 window 导出（在 IIFE 末尾添加）**

```javascript
  window.stepVideoNav = stepVideoNav;
  window.stepVideoTab = stepVideoTab;
  window.stepVideoModel = stepVideoModel;
  window.stepVideoRatio = stepVideoRatio;
  window.stepVideoUploadFirstFrame = stepVideoUploadFirstFrame;
  window.stepVideoUploadLastFrame = stepVideoUploadLastFrame;
  window.stepVideoPrompt = stepVideoPrompt;
  window.stepVideoGenerate = stepVideoGenerate;
  window.stepVideoWait = stepVideoWait;
})();
```

- [ ] **Step 11: 验证 jimeng-steps.js 语法正确**

Run: 在 Chrome DevTools Console 测试 `window.stepVideoNav` 等函数是否存在（通过 popup 测试页面调用 test:step）

---

## Task 2: 完善 content-script.js 中的 runJimengVideoJobHandler

**Files:**
- Modify: `extension/content-script.js:237-384`（现有 handler 需要重构为调用 jimeng-steps.js 的新 step 函数）

**现状分析：**
- 现有 `runJimengVideoJobHandler` 是粗糙的 inline 实现，没有调用 jimeng-steps.js 的 step 函数
- 需要重写为：按顺序调用 `stepVideoNav` → `stepVideoTab` → `stepVideoModel` → `stepVideoRatio` → `stepVideoUploadFirstFrame` → `stepVideoUploadLastFrame` → `stepVideoPrompt` → `stepVideoGenerate` → `stepVideoWait`
- 视频下载使用 `bridgeFetch` 获取 blob，转换为 base64
- 结果上报使用 `postJson` 到 `/v1/job/{id}/result`，payload 包含 `videos` 字段

- [ ] **Step 1: 重写 runJimengVideoJobHandler 调用新的 step 函数**

替换现有 `runJimengVideoJobHandler` body（第 237-384 行）：

```javascript
// Jimeng video handler — delegates to jimeng-steps.js step functions
async function runJimengVideoJobHandler(job, serverUrl) {
  const logs = [];

  const record = async (message, details = null) => {
    const at = new Date().toISOString();
    const entry = { at, message };
    if (details !== null && details !== undefined) entry.details = details;
    logs.push(entry);
    await notifyProgress(message);
    await sendProgress(serverUrl, message, at, details);
  };

  const snapshotDOM = () => {
    try {
      const comboboxes = Array.from(document.querySelectorAll('[role="combobox"]')).map(el => el.textContent.trim().slice(0, 60));
      const buttons = Array.from(document.querySelectorAll('button')).filter(el => el.getBoundingClientRect().width > 0).map(el => el.textContent.trim().slice(0, 40));
      return JSON.stringify({ comboboxes, buttons, url: window.location.href.slice(0, 80) });
    } catch { return "{}"; }
  };

  try {
    await record(`Preparing ${job.id}`);

    // S1V: Navigate to video page
    if (window.location.href !== job.targetUrl) {
      await record("Navigating to Jimeng video page");
      window.location.href = job.targetUrl;
      await waitFor(() => window.location.href.includes("type=video"), { timeoutMs: 30000, label: "jimeng video page" });
      await delay(2000);
    } else {
      await delay(1000);
    }

    await record("Waiting for page to be ready");
    await waitFor(() => document.querySelector('[role="combobox"]'), { timeoutMs: 20000, label: "combobox" });
    await delay(500);

    // S2V: Confirm video tab
    await record("Confirming video tab");
    {
      const r = await window.stepVideoTab();
      if (!r.ok) throw new Error(`[S2V] ${r.error} | DOM: ${snapshotDOM()}`);
    }
    await delay(300);

    // S3V: Select Seedance 1.0 model
    await record("Selecting Seedance 1.0 model");
    {
      const r = await window.stepVideoModel();
      if (!r.ok) throw new Error(`[S3V] ${r.error} | DOM: ${snapshotDOM()}`);
    }
    await delay(300);

    // S4V: Select aspect ratio
    await record("Selecting aspect ratio");
    {
      const r = await window.stepVideoRatio(job);
      if (!r.ok) throw new Error(`[S4V] ${r.error} | DOM: ${snapshotDOM()}`);
    }
    await delay(300);

    // S5V: Upload first frame image
    const firstFrameAsset = job.assets?.find(a => a.label === "firstFrame") || job.assets?.[0];
    if (!firstFrameAsset) throw new Error("No first frame asset found in job.assets");
    await record("Uploading first frame image");
    {
      const r = await window.stepVideoUploadFirstFrame(firstFrameAsset);
      if (!r.ok) throw new Error(`[S5V] ${r.error} | DOM: ${snapshotDOM()}`);
    }

    // S6V: Upload last frame (optional)
    const lastFrameAsset = job.assets?.find(a => a.label === "lastFrame");
    if (lastFrameAsset) {
      await record("Uploading last frame image");
      const r = await window.stepVideoUploadLastFrame(lastFrameAsset);
      // last frame is optional, don't fail if it returns skipped
    }
    await delay(300);

    // S7V: Fill movement description and prompt
    await record("Filling prompt text");
    {
      const r = await window.stepVideoPrompt(job);
      if (!r.ok) throw new Error(`[S7V] ${r.error} | DOM: ${snapshotDOM()}`);
    }
    await delay(300);

    // S8V: Click generate button
    await record("Clicking generate button");
    {
      const r = await window.stepVideoGenerate();
      if (!r.ok) throw new Error(`[S8V] ${r.error} | DOM: ${snapshotDOM()}`);
    }
    await delay(1000);

    // S9V: Wait for video result
    await record("Waiting for generated video");
    const waitResult = await window.stepVideoWait(job);
    if (!waitResult.ok) throw new Error(`[S9V] ${waitResult.error} | DOM: ${snapshotDOM()}`);

    const videoUrl = waitResult.data.videoUrl;
    console.log("[JimengVideo] stepVideoWait returned URL:", videoUrl.slice(0, 60), "source:", waitResult.data.sourceType);
    await record(`Found video from ${waitResult.data.sourceType}`);

    // Download video via bridgeFetch (extension context has proper cookie jar)
    await record("Downloading video");
    let blob, mimeType;
    try {
      const fetchResp = await bridgeFetch({ url: videoUrl, responseType: "blobBase64" });
      const binary = atob(fetchResp.base64Data);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      blob = new Blob([bytes], { type: fetchResp.mimeType || "video/mp4" });
      mimeType = blob.type || "video/mp4";
    } catch (err) {
      throw new Error(`Failed to fetch video: ${err.message}`);
    }
    const extension = mimeType.includes("webm") ? ".webm" : ".mp4";
    const base64Data = await blobToBase64(blob);

    await record("Saving results to local bridge");
    const bridgeResp = await postJson(`${serverUrl}/v1/job/${encodeURIComponent(job.id)}/result`, {
      videos: [{
        filename: `result-001${extension}`,
        mimeType,
        base64Data,
        sourceUrl: videoUrl,
      }],
      logs,
    });
    console.log("[JimengVideo] /result response:", JSON.stringify(bridgeResp).slice(0, 200));

    controllerState.lastError = null;
    controllerState.lastMessage = `Completed ${job.id}`;
    await chrome.runtime.sendMessage({ type: "content:finished", jobId: job.id, state: { ...controllerState } });

  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    console.error("[JimengVideo ERROR]", reason, "\nFull logs:", logs);
    logs.push({ at: new Date().toISOString(), message: `Failed: ${reason}` });
    try {
      await postJson(`${serverUrl}/v1/job/${encodeURIComponent(job.id)}/fail`, { reason, logs });
    } catch (_postError) { /* ignore */ }
    controllerState.lastError = reason;
    controllerState.lastMessage = `Failed ${job.id}`;
    await chrome.runtime.sendMessage({ type: "content:failed", jobId: job.id, reason, state: { ...controllerState } });
  }
}
```

- [ ] **Step 2: 更新 runJob 分发逻辑**

在 `runJob` 函数（第 386-395 行）中，将 platform="jimeng" 的判断扩展为：根据 `job.targetUrl` 区分 image 和 video：

```javascript
async function runJob(job, serverUrl) {
  const platform = job.platform || "gpt";
  if (platform === "gpt") {
    await runGptJobHandler(job, serverUrl);
  } else if (platform === "jimeng") {
    // Distinguish image vs video by targetUrl
    if (job.targetUrl && job.targetUrl.includes("type=video")) {
      await runJimengVideoJobHandler(job, serverUrl);
    } else {
      await runJimengImageJobHandler(job, serverUrl);
    }
  } else {
    throw new Error(`Unknown platform: ${platform}`);
  }
}
```

- [ ] **Step 3: 验证 handler 重构正确**

Run: `git diff extension/content-script.js` 确认 handler 和 runJob 分发修改无误

---

## Task 3: 在 content-script.js 添加 test:step 的 video 测试支持

**Files:**
- Modify: `extension/content-script.js`（在 `runTestStep` 函数中新增 video 测试步骤）

- [ ] **Step 1: 在 runTestStep 中添加 s1v-s9v 测试步骤**

在 `runTestStep` 的 switch 语句中添加：

```javascript
case "s1v_nav": {
  const target = "https://jimeng.jianying.com/ai-tool/home/?type=video&workspace=0";
  const result = await window.stepVideoNav(target);
  if (!result.ok) return "ERROR: " + result.error;
  return result.data.status === "navigating" ? "Navigating to jimeng.jianying.com (type=video)..." : "Already on target page: " + result.data.url;
}
case "s2v_tab": {
  const result = await window.stepVideoTab();
  if (!result.ok) return "ERROR: " + result.error;
  return "OK: Video tab ready - " + JSON.stringify(result.data);
}
case "s3v_model": {
  const result = await window.stepVideoModel();
  if (!result.ok) return "ERROR: " + result.error;
  return "OK: Model set - " + JSON.stringify(result.data);
}
case "s4v_ratio": {
  const result = await window.stepVideoRatio({});
  if (!result.ok) return "ERROR: " + result.error;
  return "OK: Ratio selected - " + JSON.stringify(result.data);
}
case "s5v_firstframe": {
  // S5V test — check first frame upload zone is present
  const zones = Array.from(document.querySelectorAll("[class*='reference-upload-']")).filter(el => {
    return isVisible(el);
  });
  if (zones.length > 0) return "OK: First frame upload zone present (" + zones.length + " zones). Full flow requires job.assets.";
  return "WARN: No upload zone found";
}
case "s6v_prompt": {
  // S6V test — check prompt textareas are present
  const textareas = Array.from(document.querySelectorAll("textarea")).filter(el =>
    isVisible(el) && el.placeholder.includes("运动方式")
  );
  if (textareas.length > 0) return "OK: Prompt textareas found (" + textareas.length + "). Full flow uses job.prompt.";
  return "WARN: No prompt textarea found";
}
case "s7v_generate": {
  const result = await window.stepVideoGenerate();
  if (!result.ok) return "ERROR: " + result.error;
  return "OK: Clicked generate button";
}
case "s8v_wait": {
  const result = await window.stepVideoWait({ timeoutSeconds: 60 });
  if (!result.ok) return "ERROR: " + result.error;
  window.__testResultVideo = result.data;
  return "OK: Found video URL: " + result.data.videoUrl.slice(0, 50) + " source:" + result.data.sourceType;
}
case "s9v_download": {
  const videoData = window.__testResultVideo;
  if (!videoData) return "ERROR: Run s8v_wait first";
  try {
    const fetchResp = await bridgeFetch({ url: videoData.videoUrl, responseType: "blobBase64" });
    const binary = atob(fetchResp.base64Data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const blob = new Blob([bytes], { type: fetchResp.mimeType || "video/mp4" });
    const base64 = await blobToBase64(blob);
    const ext = fetchResp.mimeType?.includes("webm") ? ".webm" : ".mp4";
    window.__testVideoResult = { blob, base64, mimeType: blob.type || "video/mp4", ext };
    return "OK: Downloaded video (" + (fetchResp.base64Data.length / 1024 / 1024).toFixed(1) + "MB)";
  } catch (err) {
    return "ERROR: Failed to download video: " + err.message;
  }
}
```

同时更新 `runTestStep` 的 platform 检查（line 1182），使其接受 "jimeng-video" 或在 jimeng 分支中再区分 image/video：

```javascript
if (platform !== "jimeng" && platform !== "jimeng-video") {
  return "ERROR: Only jimeng/jimeng-video supported for now";
}
```

---

## Task 4: 更新 CLAUDE.md 文档

**Files:**
- Modify: `CLAUDE.md`（在"核心文件"和"platform handler"部分补充 jimeng video 说明）

- [ ] **Step 1: 更新 platform handler 说明**

在 CLAUDE.md 的 platform handler 部分添加：
```
- `jimeng-video.js` → `runJimengVideoJobHandler` → jimeng.jianying.com（视频模式，type=video）
```

在核心文件表中添加：
```
| `extension/jimeng-steps.js` | 共享 step 函数（含 image S1-S8 + video S1V-S9V） |
```

---

## Self-Review Checklist

**1. Spec coverage:**
- [x] S1V 导航到 type=video → Task 1 Step 1
- [x] S2V 确认视频 tab → Task 1 Step 2
- [x] S3V 选择 Seedance 1.0 → Task 1 Step 3
- [x] S4V 选择比例 → Task 1 Step 4
- [x] S5V 上传首帧 → Task 1 Step 5
- [x] S6V 上传尾帧（可选）→ Task 1 Step 6
- [x] S7V 填写运动描述+prompt → Task 1 Step 7
- [x] S8V 点击生成 → Task 1 Step 8
- [x] S9V 等待视频 → Task 1 Step 9
- [x] Handler 调用 steps → Task 2 Step 1
- [x] runJob 分发 image/video → Task 2 Step 2
- [x] 测试步骤 → Task 3
- [x] 文档更新 → Task 4

**2. Placeholder scan:** 无 TBD/TODO，所有 step 函数代码完整，每个 Task 的 Step 都有实际代码块。

**3. Type consistency:**
- `stepVideoWait` 返回 `{ ok, data: { videoUrl, sourceType }, error }` — 与 `stepWait`（返回 `{ ok, data: { images }, error }`）模式一致
- `runJimengVideoJobHandler` 的 result payload 使用 `videos` 字段（区别于 image 的 `images` 字段）
- job.assets 的 label 约定：`firstFrame`（首帧）、`lastFrame`（尾帧）— 与 image 的 `人物/服装/场景` 不同

**4. 视频上传到 Media AI API：** 计划未涵盖视频文件上传到 `/api/videos` 的逻辑（只涵盖本地 bridge 结果上报）。如需在 bridge 层上传视频，需在 `server.py` 的 `/v1/job/{id}/result` handler 中增加视频上传到 `/api/videos` 的逻辑。需确认这是否是真实需求再决定是否扩展 Task 2。