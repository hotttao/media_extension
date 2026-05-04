// GPT handler (inline — no module import needed)
async function runGptJobHandler(job, serverUrl) {
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

// Jimeng image handler (inline — mirrors jimeng-image.js logic)
async function runJimengImageJobHandler(job, serverUrl) {
  const logs = [];

  const record = async (message, details = null) => {
    const at = new Date().toISOString();
    const entry = { at, message };
    if (details !== null && details !== undefined) { entry.details = details; }
    logs.push(entry);
    await notifyProgress(message);
    await sendProgress(serverUrl, message, at, details);
  };

  const snapshotDOM = () => {
    try {
      const comboboxes = Array.from(document.querySelectorAll('[role="combobox"]')).map(el => el.textContent.trim().slice(0, 60));
      const buttons = Array.from(document.querySelectorAll('button')).filter(el => el.getBoundingClientRect().width > 0).map(el => el.textContent.trim().slice(0, 40));
      const fileInputs = Array.from(document.querySelectorAll('input[type="file"]')).length;
      return JSON.stringify({ comboboxes, buttons, fileInputs, url: window.location.href.slice(0, 80) });
    } catch { return "{}"; }
  };

  try {
    await record(`Preparing ${job.id}`);

    if (window.location.href !== job.targetUrl) {
      await record("Navigating to Jimeng");
      window.location.href = job.targetUrl;
      await waitFor(() => window.location.href.includes("type=image"), { timeoutMs: 30000, label: "jimeng image page" });
      await delay(2000);
    } else {
      await delay(1000);
    }

    await record("Waiting for page to be ready");
    await waitFor(() => document.querySelector('[role="combobox"]'), { timeoutMs: 20000, label: "combobox" });
    await waitFor(() => document.querySelector('input[type="file"]'), { timeoutMs: 10000, label: "file_input" });
    await delay(500);

    await record("Selecting model 图片5.0 Lite");
    {
      const r = await window.stepModel();
      if (!r.ok) { throw new Error(`[S3] ${r.error} | DOM: ${snapshotDOM()}`); }
    }
    await delay(300);

    await record("Selecting ratio 9:16 and resolution 2K");
    {
      const r = await window.stepRatio();
      if (!r.ok) { throw new Error(`[S4] ${r.error} | DOM: ${snapshotDOM()}`); }
    }
    await delay(300);

    await record("Uploading reference images");
    {
      const r = await window.stepUpload(job);
      if (!r.ok) { throw new Error(`[S5] ${r.error} | DOM: ${snapshotDOM()}`); }
    }

    await record("Writing prompt");
    {
      const r = await window.stepPrompt(job);
      if (!r.ok) { throw new Error(`[S6] ${r.error} | DOM: ${snapshotDOM()}`); }
    }

    await record("Clicking generate button");
    {
      const r = await window.stepGenerate();
      if (!r.ok) { throw new Error(`[S7] ${r.error} | DOM: ${snapshotDOM()}`); }
    }
    await delay(1000);

    await record("Waiting for generated images");
    const waitResult = await window.stepWait(job);
    if (!waitResult.ok) { throw new Error(`[S8] ${waitResult.error} | DOM: ${snapshotDOM()}`); }

    const resultImages = waitResult.data.images;
    await record(`Found ${resultImages.length} generated image(s)`);

    const serializedImages = [];
    for (let i = 0; i < resultImages.length; i++) {
      const img = resultImages[i];
      try {
        const response = await fetch(img.src, { credentials: "include" });
        if (!response.ok) continue;
        const blob = await response.blob();
        const mimeType = blob.type || "image/png";
        const base64 = await blobToBase64(blob);
        const ext = ({ "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif" })[mimeType] || ".png";
        serializedImages.push({
          filename: `result-${String(i + 1).padStart(2, "0")}${ext}`,
          mimeType,
          base64Data: base64,
          sourceUrl: img.src,
        });
      } catch (err) {
        await record(`Failed to serialize image ${i + 1}: ${err.message}`);
      }
    }

    await record("Saving results to local bridge", { imageCount: serializedImages.length });
    await postJson(`${serverUrl}/v1/job/${encodeURIComponent(job.id)}/result`, {
      images: serializedImages,
      logs,
    });

    controllerState.lastError = null;
    controllerState.lastMessage = `Completed ${job.id}`;
    await chrome.runtime.sendMessage({ type: "content:finished", jobId: job.id, state: { ...controllerState } });

  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    console.error("[JimengImage ERROR]", reason, "\nFull logs:", logs);
    logs.push({ at: new Date().toISOString(), message: `Failed: ${reason}` });
    try {
      await postJson(`${serverUrl}/v1/job/${encodeURIComponent(job.id)}/fail`, { reason, logs });
    } catch (_postError) { /* ignore */ }
    controllerState.lastError = reason;
    controllerState.lastMessage = `Failed ${job.id}`;
    await chrome.runtime.sendMessage({ type: "content:failed", jobId: job.id, reason, state: { ...controllerState } });
  }
}

// Jimeng video handler (inline)
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

  const fetchAssetAsFileVideo = async (asset) => {
    const response = await bridgeFetch({ url: asset.url, responseType: "blobBase64" });
    const binary = atob(response.base64Data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const mimeType = asset.mimeType || response.mimeType || "application/octet-stream";
    return new File([bytes], asset.name, { type: mimeType });
  };

  const uploadFirstFrameImage = async (asset) => {
    const fileInput = await waitFor(() => Array.from(document.querySelectorAll("input[type='file']")).find(input => isVisible(input) || input.offsetParent !== null), { timeoutMs: 30000, label: "file input for image upload" });
    if (!fileInput) throw new Error("File input not found for image upload");
    const file = await fetchAssetAsFileVideo(asset);
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(file);
    fileInput.files = dataTransfer.files;
    fileInput.dispatchEvent(new Event("change", { bubbles: true }));
    fileInput.dispatchEvent(new Event("input", { bubbles: true }));
    await delay(2000);
  };

  const fillInput = (input, text) => {
    input.focus();
    const currentValue = input.value || "";
    if (currentValue === text) return;
    if ("value" in input) {
      input.value = "";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.value = text;
      input.dispatchEvent(new InputEvent("input", { bubbles: true, data: text, inputType: "insertText" }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    } else {
      const inserted = document.execCommand("insertText", false, text);
      if (!inserted) {
        input.textContent = text;
        input.dispatchEvent(new InputEvent("input", { bubbles: true, data: text, inputType: "insertText" }));
      }
    }
    input.blur();
  };

  const waitForVideoResult = async (timeoutMs) => {
    const deadline = Date.now() + timeoutMs;
    let stableSince = 0;
    let lastVideoSrc = "";
    while (Date.now() < deadline) {
      const videoElement = document.querySelector("video");
      if (videoElement && isVisible(videoElement) && videoElement.src && videoElement.src !== lastVideoSrc) {
        lastVideoSrc = videoElement.src;
        if (!stableSince) stableSince = Date.now();
        if (Date.now() - stableSince > 8000) return { sourceType: "videoElement", url: videoElement.src, element: videoElement };
      }
      const downloadLink = Array.from(document.querySelectorAll("a[href]")).find(a => a.href && (a.href.includes(".mp4") || a.href.includes(".webm")));
      if (downloadLink && downloadLink.href !== lastVideoSrc) {
        lastVideoSrc = downloadLink.href;
        if (!stableSince) stableSince = Date.now();
        if (Date.now() - stableSince > 8000) return { sourceType: "downloadLink", url: downloadLink.href, element: downloadLink };
      }
      await delay(2000);
    }
    throw new Error("Timed out while waiting for video result");
  };

  try {
    await record(`Preparing ${job.id}`);

    if (window.location.href !== job.targetUrl) {
      await record("Navigating to Jimeng video page");
      window.location.href = job.targetUrl;
      await waitFor(() => window.location.href.includes("jimeng.jianying.com"), { timeoutMs: 30000, label: "page navigation" });
      await delay(2000);
    }

    await record("Clicking 视频生成 tab");
    const videoTab = await waitFor(() => Array.from(document.querySelectorAll("div, span, button")).find(el => isVisible(el) && el.innerText && el.innerText.includes("视频生成")), { timeoutMs: 30000, label: "视频生成 tab" });
    if (videoTab) { videoTab.click(); await delay(1000); }

    await record("Selecting Seedance1.0 首尾帧 model");
    const modelOption = await waitFor(() => Array.from(document.querySelectorAll("div, span, button")).find(el => isVisible(el) && el.innerText && el.innerText.includes("Seedance1.0 首尾帧")), { timeoutMs: 30000, label: "Seedance1.0 model option" });
    if (modelOption) { modelOption.click(); await delay(1000); }

    await record("Uploading first frame image");
    const firstFrameAsset = job.assets?.find(a => a.label === "firstFrame") || (job.assets?.length > 0 ? job.assets[0] : null);
    if (firstFrameAsset) await uploadFirstFrameImage(firstFrameAsset);

    await record("Filling movement description");
    const movementText = job.movement || job.movementId || job.prompt || "";
    const movementInput = await waitFor(() => Array.from(document.querySelectorAll("textarea, input")).find(el => isVisible(el) && (el.placeholder?.includes("运动") || el.placeholder?.includes("movement"))), { timeoutMs: 30000, label: "movement input" });
    if (movementInput) { fillInput(movementInput, movementText); await delay(500); }

    await record("Filling prompt text");
    const promptInput = await waitFor(() => Array.from(document.querySelectorAll("textarea")).find(el => isVisible(el) && (el.placeholder?.includes("描述") || el.placeholder?.includes("prompt"))), { timeoutMs: 30000, label: "prompt input" });
    if (promptInput) { fillInput(promptInput, job.prompt || ""); await delay(500); }

    await record("Clicking generate button");
    const generateButton = await waitFor(() => Array.from(document.querySelectorAll("button")).find(el => isVisible(el) && !el.disabled && (el.innerText?.includes("生成") || el.innerText?.includes("生成视频"))), { timeoutMs: 30000, label: "generate button" });
    if (!generateButton) throw new Error("Generate button not found");
    generateButton.click();

    await record("Waiting for video result");
    const videoResult = await waitForVideoResult(job.timeoutSeconds ? job.timeoutSeconds * 1000 : 600000);
    await record(`Found video result`, { sourceType: videoResult.sourceType, url: videoResult.url });

    await record("Serializing video");
    let blob, mimeType = "video/mp4";
    if (videoResult.sourceType === "videoElement") {
      const response = await fetch(videoResult.url, { credentials: "include" });
      if (!response.ok) throw new Error(`Failed to fetch video: ${response.status}`);
      blob = await response.blob();
      mimeType = blob.type || "video/mp4";
    } else {
      const response = await fetch(videoResult.url, { credentials: "include" });
      if (!response.ok) throw new Error(`Failed to fetch video from download link: ${response.status}`);
      blob = await response.blob();
      mimeType = blob.type || "video/mp4";
    }
    const extension = mimeType.includes("webm") ? ".webm" : ".mp4";
    const base64Data = await blobToBase64(blob);

    await postJson(`${serverUrl}/v1/job/${encodeURIComponent(job.id)}/result`, {
      videos: [{ filename: `result-001${extension}`, mimeType, base64Data, sourceUrl: videoResult.url }],
      logs,
    });

    controllerState.lastError = null;
    controllerState.lastMessage = `Completed ${job.id}`;
    await chrome.runtime.sendMessage({ type: "content:finished", jobId: job.id, state: { ...controllerState } });
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    logs.push({ at: new Date().toISOString(), message: `Failed: ${reason}` });
    try { await postJson(`${serverUrl}/v1/job/${encodeURIComponent(job.id)}/fail`, { reason, logs }); } catch (_postError) { /* Ignore */ }
    controllerState.lastError = reason;
    controllerState.lastMessage = `Failed ${job.id}`;
    await chrome.runtime.sendMessage({ type: "content:failed", jobId: job.id, reason, state: { ...controllerState } });
  }
}

async function runJob(job, serverUrl) {
  const platform = job.platform || "gpt";
  if (platform === "gpt") {
    await runGptJobHandler(job, serverUrl);
  } else if (platform === "jimeng_image") {
    await runJimengImageJobHandler(job, serverUrl);
  } else if (platform === "jimeng_video") {
    await runJimengVideoJobHandler(job, serverUrl);
  } else {
    throw new Error(`Unknown platform: ${platform}`);
  }
}

const DEFAULT_TIMEOUT_MS = 15 * 60 * 1000;
const SUBMISSION_EFFECT_TIMEOUT_MS = 120 * 1000;
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

let pollTimer = null;
let heartbeatTimer = null;

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function isVisible(element) {
  if (!element) {
    return false;
  }
  const style = window.getComputedStyle(element);
  if (style.display === "none" || style.visibility === "hidden") {
    return false;
  }
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

// Text comparison helpers — compare by character codes to avoid encoding mismatches
// between JS source (UTF-8) and DOM text content
function charCodesOf(str) {
  return Array.from(str).map(c => c.charCodeAt(0));
}
function sameChars(a, b) {
  const ca = charCodesOf(a);
  const cb = charCodesOf(b);
  if (ca.length !== cb.length) return false;
  return ca.every((c, i) => c === cb[i]);
}
function textLike(domText, target) {
  if (!domText) return false;
  const dt = domText.trim();
  if (dt === target) return true;
  return sameChars(dt, target);
}
function textIncludes(domText, target) {
  if (!domText) return false;
  const dt = domText.trim();
  if (dt.includes(target)) return true;
  // Fallback: char-code substring search
  const dc = charCodesOf(dt);
  const tc = charCodesOf(target);
  if (tc.length > dc.length) return false;
  outer: for (let i = 0; i <= dc.length - tc.length; i++) {
    for (let j = 0; j < tc.length; j++) {
      if (dc[i + j] !== tc[j]) continue outer;
    }
    return true;
  }
  return false;
}

function sanitizeText(value, maxLength = 240) {
  return String(value || "").replace(/\s+/g, " ").trim().slice(0, maxLength);
}

function getElementPath(element) {
  const parts = [];
  let current = element;

  while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 6) {
    const tag = current.tagName.toLowerCase();
    const id = current.id ? `#${current.id}` : "";
    let part = `${tag}${id}`;
    if (!id && current.parentElement) {
      const siblings = Array.from(current.parentElement.children).filter((child) => child.tagName === current.tagName);
      if (siblings.length > 1) {
        part += `:nth-of-type(${siblings.indexOf(current) + 1})`;
      }
    }
    parts.unshift(part);
    current = current.parentElement;
  }

  return parts.join(" > ");
}

async function bridgeFetch(request) {
  const response = await chrome.runtime.sendMessage({ type: "bridge:fetch", request });
  if (!response?.ok) {
    throw new Error(response?.error || "Bridge fetch failed");
  }
  return response;
}

async function postJson(url, payload) {
  const response = await bridgeFetch({
    url,
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
    responseType: "json",
  });
  return response.json;
}

async function notifyProgress(message) {
  controllerState.lastMessage = message;
  try {
    await chrome.runtime.sendMessage({ type: "content:progress", message, state: { ...controllerState } });
  } catch (_error) {
    // Ignore popup sync failures.
  }
}

async function sendProgress(serverUrl, message, at, details = null) {
  if (!serverUrl || !controllerState.currentJobId) {
    return;
  }
  await postJson(`${serverUrl}/v1/job/${encodeURIComponent(controllerState.currentJobId)}/progress`, {
    message,
    at,
    details,
  });
}

async function waitFor(predicate, options = {}) {
  const timeoutMs = options.timeoutMs ?? 120000;
  const intervalMs = options.intervalMs ?? 250;
  const label = options.label ?? "condition";
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const value = predicate();
    if (value) {
      return value;
    }
    await delay(intervalMs);
  }

  throw new Error(`Timed out while waiting for ${label}`);
}

function composerCandidates() {
  return [
    document.querySelector("textarea"),
    document.querySelector("#prompt-textarea"),
    document.querySelector("div[contenteditable='true'][role='textbox']"),
    document.querySelector("div[contenteditable='true'][data-lexical-editor='true']"),
  ].filter(Boolean);
}

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
  if ("value" in composer) {
    composer.value = "";
    composer.dispatchEvent(new Event("input", { bubbles: true }));
    composer.dispatchEvent(new Event("change", { bubbles: true }));
    return;
  }

  composer.focus();
  document.getSelection()?.removeAllRanges();
  const range = document.createRange();
  range.selectNodeContents(composer);
  const selection = document.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
  document.execCommand("delete");
}

function setComposerText(composer, text) {
  clearComposer(composer);

  if ("value" in composer) {
    composer.focus();
    composer.value = text;
    composer.dispatchEvent(new InputEvent("input", { bubbles: true, data: text, inputType: "insertText" }));
    composer.dispatchEvent(new Event("change", { bubbles: true }));
    return;
  }

  composer.focus();
  const inserted = document.execCommand("insertText", false, text);
  if (!inserted) {
    composer.textContent = text;
    composer.dispatchEvent(new InputEvent("input", { bubbles: true, data: text, inputType: "insertText" }));
  }
}

function findAttachButton() {
  const selectors = [
    "button[aria-label*='Attach']",
    "button[aria-label*='attach']",
    "button[aria-label*='photo']",
    "button[aria-label*='file']",
    "button[data-testid*='upload']",
  ];

  for (const selector of selectors) {
    const button = Array.from(document.querySelectorAll(selector)).find((candidate) => isVisible(candidate));
    if (button) {
      return button;
    }
  }
  return null;
}

async function ensureFileInput() {
  let input = document.querySelector("input[type='file']");
  if (input) {
    return input;
  }

  const attachButton = findAttachButton();
  if (attachButton) {
    attachButton.click();
  }

  input = await waitFor(() => document.querySelector("input[type='file']"), {
    timeoutMs: 120000,
    label: "file input",
  });
  return input;
}

async function fetchAssetAsFile(asset) {
  const response = await bridgeFetch({
    url: asset.url,
    responseType: "blobBase64",
  });

  const binary = atob(response.base64Data);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  const mimeType = asset.mimeType || response.mimeType || "application/octet-stream";
  const blob = new Blob([bytes], { type: mimeType });
  return new File([blob], asset.name, { type: mimeType });
}

async function uploadAssets(job) {
  if (!job.assets?.length) {
    return;
  }

  const input = await ensureFileInput();
  const files = await Promise.all(job.assets.map((asset) => fetchAssetAsFile(asset)));

  if (input.multiple) {
    const transfer = new DataTransfer();
    for (const file of files) {
      transfer.items.add(file);
    }
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    input.dispatchEvent(new Event("input", { bubbles: true }));
  } else {
    for (const file of files) {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  await waitForUploadComplete(files.length);
}

function describeButton(button) {
  return {
    path: getElementPath(button),
    text: sanitizeText(button.innerText || button.textContent || ""),
    ariaLabel: button.getAttribute("aria-label"),
    title: button.getAttribute("title"),
    dataTestId: button.getAttribute("data-testid"),
    type: button.getAttribute("type"),
    disabled: Boolean(button.disabled),
  };
}

function collectVisibleButtons(limit = 15) {
  return Array.from(document.querySelectorAll("button"))
    .filter((button) => isVisible(button))
    .slice(0, limit)
    .map((button) => describeButton(button));
}

function findComposerForm(composer) {
  return composer.closest("form");
}

function findSendButton(composer) {
  const searchRoots = [findComposerForm(composer), composer.parentElement, document].filter(Boolean);
  const selectors = [
    "button[data-testid='send-button']",
    "button[type='submit']",
    "button[aria-label*='Send']",
    "button[aria-label*='send']",
    "button[data-testid*='send']",
  ];

  for (const root of searchRoots) {
    for (const selector of selectors) {
      const button = Array.from(root.querySelectorAll(selector)).find((candidate) => isVisible(candidate) && !candidate.disabled);
      if (button) {
        return button;
      }
    }
  }

  return null;
}

function dispatchEnter(composer) {
  composer.focus();
  const eventInit = { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true };
  composer.dispatchEvent(new KeyboardEvent("keydown", eventInit));
  composer.dispatchEvent(new KeyboardEvent("keypress", eventInit));
  composer.dispatchEvent(new KeyboardEvent("keyup", eventInit));
}

function getAssistantTurnElements() {
  return Array.from(
    document.querySelectorAll("section[data-turn='assistant'][data-testid^='conversation-turn-']")
  ).filter((element) => isVisible(element));
}

function collectImageEntries(root = document) {
  const imageCandidates = Array.from(
    root.querySelectorAll("img[src*='/backend-api/estuary/content?id=file_']")
  ).filter((img) => {
    if (!isVisible(img)) {
      return false;
    }
    const rect = img.getBoundingClientRect();
    const width = img.naturalWidth || rect.width;
    const height = img.naturalHeight || rect.height;
    return width >= 200 && height >= 200;
  });

  const deduped = new Map();
  for (const img of imageCandidates) {
    const key = img.currentSrc || img.src || "";
    if (!key || deduped.has(key)) {
      continue;
    }
    deduped.set(key, {
      key,
      element: img,
    });
  }

  return Array.from(deduped.values());
}

function collectImageKeys(root = document) {
  return new Set(collectImageEntries(root).map((entry) => entry.key));
}

async function waitForUploadComplete(expectedCount) {
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline) {
    const uploadedImages = collectImageEntries(getImageSearchRoot())
      .filter((e) => e.key.includes("file_"));
    if (uploadedImages.length >= expectedCount) {
      return true;
    }
    await delay(1000);
  }
  return false;
}

function getImageSearchRoot() {
  return document.querySelector("main") || document;
}

function collectAllAssistantImageKeys() {
  const keys = new Set();
  for (const turn of getAssistantTurnElements()) {
    for (const image of collectImageEntries(turn)) {
      keys.add(image.key);
    }
  }
  return keys;
}

function describeAssistantTurn(turnElement, imageEntries) {
  return {
    path: getElementPath(turnElement),
    tagName: turnElement.tagName.toLowerCase(),
    dataTurn: turnElement.getAttribute("data-turn"),
    dataTestId: turnElement.getAttribute("data-testid"),
    textSnippet: sanitizeText(turnElement.innerText || turnElement.textContent || ""),
    imageCount: imageEntries.length,
    imageSources: imageEntries.map((entry) => entry.key),
  };
}

async function waitForSubmissionEffect(composer, baselineAssistantCount) {
  const originalText = getComposerText(composer).trim();
  const deadline = Date.now() + SUBMISSION_EFFECT_TIMEOUT_MS;

  while (Date.now() < deadline) {
    const currentText = getComposerText(composer).trim();
    const assistantCount = getAssistantTurnElements().length;
    if (currentText !== originalText || currentText.length === 0 || assistantCount > baselineAssistantCount) {
      return true;
    }
    await delay(300);
  }

  return false;
}

async function submitPrompt(composer, baselineAssistantCount) {
  const sendButton = findSendButton(composer);
  if (sendButton) {
    sendButton.click();
    const submitted = await waitForSubmissionEffect(composer, baselineAssistantCount);
    return {
      method: "button-click",
      submitted,
      button: describeButton(sendButton),
    };
  }

  const form = findComposerForm(composer);
  if (form && typeof form.requestSubmit === "function") {
    form.requestSubmit();
    const submitted = await waitForSubmissionEffect(composer, baselineAssistantCount);
    if (submitted) {
      return {
        method: "form-request-submit",
        submitted: true,
      };
    }
  }

  dispatchEnter(composer);
  const submitted = await waitForSubmissionEffect(composer, baselineAssistantCount);
  return {
    method: "keyboard-enter",
    submitted,
  };
}

async function waitForAssistantResponseImages(baselineAssistantImageKeys, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let stableSince = 0;
  let lastKeys = [];

  while (Date.now() < deadline) {
    const assistantTurns = getAssistantTurnElements();
    let matchedTurn = null;
    let matchedImages = [];

    for (let index = assistantTurns.length - 1; index >= 0; index -= 1) {
      const turn = assistantTurns[index];
      const images = collectImageEntries(turn).filter((entry) => !baselineAssistantImageKeys.has(entry.key));
      if (images.length > 0) {
        matchedTurn = turn;
        matchedImages = images;
        break;
      }
    }

    if (!matchedTurn) {
      await delay(2000);
      continue;
    }

    const currentKeys = matchedImages.map((entry) => entry.key).sort();
    const sameAsPrevious =
      currentKeys.length === lastKeys.length && currentKeys.every((key, index) => key === lastKeys[index]);

    if (sameAsPrevious) {
      if (!stableSince) {
        stableSince = Date.now();
      }
      if (Date.now() - stableSince > 8000) {
        return {
          images: matchedImages,
          assistantTurn: describeAssistantTurn(matchedTurn, matchedImages),
        };
      }
    } else {
      stableSince = Date.now();
      lastKeys = currentKeys;
    }

    await delay(2000);
  }

  throw new Error("Timed out while waiting for generated images in the assistant response");
}

async function waitForGeneratedImagesAnywhere(baselineImageKeys, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let stableSince = 0;
  let lastKeys = [];

  while (Date.now() < deadline) {
    const currentEntries = collectImageEntries(getImageSearchRoot()).filter((entry) => !baselineImageKeys.has(entry.key));
    const currentKeys = currentEntries.map((entry) => entry.key).sort();

    if (currentKeys.length > 0) {
      const sameAsPrevious =
        currentKeys.length === lastKeys.length && currentKeys.every((key, index) => key === lastKeys[index]);
      if (sameAsPrevious) {
        if (!stableSince) {
          stableSince = Date.now();
        }
        if (Date.now() - stableSince > 8000) {
          return {
            images: currentEntries,
            assistantTurn: null,
          };
        }
      } else {
        stableSince = Date.now();
        lastKeys = currentKeys;
      }
    }

    await delay(2000);
  }

  throw new Error("Timed out while waiting for generated images on the page");
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = String(reader.result || "");
      const commaIndex = result.indexOf(",");
      resolve(commaIndex >= 0 ? result.slice(commaIndex + 1) : result);
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

function extensionFromMimeType(mimeType) {
  const mapping = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
  };
  return mapping[mimeType] || ".png";
}

async function serializeImages(entries) {
  const images = [];
  for (let index = 0; index < entries.length; index += 1) {
    const sourceUrl = entries[index].key;
    const response = await fetch(sourceUrl, { credentials: "include" });
    if (!response.ok) {
      throw new Error(`Failed to fetch generated image: ${response.status}`);
    }
    const blob = await response.blob();
    const mimeType = blob.type || "image/png";
    images.push({
      filename: `result-${String(index + 1).padStart(2, "0")}${extensionFromMimeType(mimeType)}`,
      mimeType,
      base64Data: await blobToBase64(blob),
      sourceUrl,
    });
  }
  return images;
}

async function claimJob(serverUrl) {
  const response = await bridgeFetch({
    url: `${serverUrl}/v1/job/claim`,
    headers: { "X-Worker-Id": `chat-page-${location.hostname}` },
    responseType: "json",
  });
  return response.json;
}

async function sendHeartbeat() {
  if (!controllerState.currentJobId || !controllerState.serverUrl) {
    return;
  }
  await postJson(`${controllerState.serverUrl}/v1/job/${encodeURIComponent(controllerState.currentJobId)}/heartbeat`, {});
}

function isJobNotFoundError(error) {
  const message = String(error || "");
  return message.includes("job_not_found") || message.includes('404: {"error": "job_not_found"}');
}

function clearHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

function startHeartbeat() {
  clearHeartbeat();
  heartbeatTimer = window.setInterval(() => {
    sendHeartbeat().catch((error) => {
      if (isJobNotFoundError(error)) {
        clearHeartbeat();
        controllerState.running = false;
        controllerState.busy = false;
        controllerState.currentJobId = null;
        controllerState.lastError = "Server queue changed. Click Start again.";
        controllerState.lastMessage = "Heartbeat stopped";
        notifyProgress("Heartbeat stopped").catch(() => {});
        return;
      }
      controllerState.lastError = String(error);
      notifyProgress("Heartbeat failed").catch(() => {});
    });
  }, HEARTBEAT_INTERVAL_MS);
}

function scheduleNextPoll(delayMs = POLL_INTERVAL_MS) {
  if (pollTimer) {
    clearTimeout(pollTimer);
  }
  pollTimer = window.setTimeout(() => {
    pollForJobs().catch((error) => {
      controllerState.lastError = String(error);
      controllerState.lastMessage = "Polling failed";
      notifyProgress("Polling failed").catch(() => {});
      if (controllerState.running) {
        scheduleNextPoll(POLL_INTERVAL_MS);
      }
    });
  }, delayMs);
}

function startController(serverUrl) {
  controllerState.serverUrl = serverUrl || controllerState.serverUrl;
  controllerState.running = true;
  controllerState.lastError = null;
  controllerState.lastMessage = "Controller started";
  scheduleNextPoll(50);
  return { ...controllerState };
}

function stopController() {
  controllerState.running = false;
  controllerState.busy = false;
  controllerState.currentJobId = null;
  controllerState.lastError = null;
  controllerState.lastMessage = "Controller stopped";
  clearHeartbeat();
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
  return { ...controllerState };
}

async function pollForJobs() {
  if (!controllerState.running || controllerState.busy) {
    return;
  }

  const payload = await claimJob(controllerState.serverUrl);
  if (!payload.job) {
    controllerState.lastError = null;
    await notifyProgress("No pending jobs");
    scheduleNextPoll(POLL_INTERVAL_MS);
    return;
  }

  controllerState.busy = true;
  controllerState.currentJobId = payload.job.id;
  controllerState.lastError = null;
  await notifyProgress(`Running ${payload.job.id}`);
  startHeartbeat();

  try {
    await runJob(payload.job, controllerState.serverUrl);
  } catch (error) {
    const reason = String(error);
    controllerState.lastError = reason;
    if (controllerState.currentJobId) {
      try {
        await postJson(`${controllerState.serverUrl}/v1/job/${encodeURIComponent(controllerState.currentJobId)}/fail`, { reason });
      } catch (_failError) {
        // Ignore bridge errors
      }
    }
  } finally {
    clearHeartbeat();
    controllerState.busy = false;
    controllerState.currentJobId = null;
    if (controllerState.running) {
      scheduleNextPoll(POLL_INTERVAL_MS);
    }
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "ping") {
    sendResponse({ ok: true });
    return true;
  }

  if (message?.type === "controller:start") {
    sendResponse({ ok: true, state: startController(message.serverUrl) });
    return true;
  }

  if (message?.type === "controller:stop") {
    sendResponse({ ok: true, state: stopController() });
    return true;
  }

  if (message?.type === "controller:runSingleJob") {
    controllerState.serverUrl = message.serverUrl || controllerState.serverUrl;
    controllerState.running = true;
    controllerState.busy = true;
    controllerState.currentJobId = message.job?.id || null;
    controllerState.lastError = null;
    controllerState.lastMessage = `Running ${controllerState.currentJobId || "job"}`;
    runJob(message.job, controllerState.serverUrl)
      .then(() => {
        controllerState.busy = false;
        controllerState.currentJobId = null;
        sendResponse({ ok: true, state: { ...controllerState } });
      })
      .catch(async (error) => {
        const reason = String(error);
        controllerState.lastError = reason;
        controllerState.lastMessage = `Failed ${controllerState.currentJobId || "job"}: ${reason}`;
        // Sync failure to bridge so job status is marked failed with reason
        if (controllerState.currentJobId) {
          try {
            await postJson(
              `${controllerState.serverUrl}/v1/job/${encodeURIComponent(controllerState.currentJobId)}/fail`,
              { reason }
            );
          } catch (_failError) {
            // Bridge call failed — still report to caller
          }
        }
        controllerState.busy = false;
        controllerState.currentJobId = null;
        sendResponse({ ok: false, error: reason, state: { ...controllerState } });
      });
    return true;
  }

  if (message?.type === "controller:getState") {
    sendResponse({ ok: true, state: { ...controllerState } });
    return true;
  }

  if (message?.type === "test:step") {
    const { platform, step } = message;
    runTestStep(platform, step)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
    return true;
  }

  return false;
});

async function runTestStep(platform, step) {
  if (platform !== "jimeng_image") {
    return "ERROR: Only jimeng_image supported for now";
  }

  // Import shared step functions
  // Shared step functions are on window (set by jimeng-steps.js content script)
  switch (step) {
    case "s1_nav": {
      const target = "https://jimeng.jianying.com/ai-tool/home/?type=image&workspace=0";
      const result = await window.stepNav(target);
      if (!result.ok) return "ERROR: " + result.error;
      return result.data.status === "navigating" ? "Navigating to jimeng.jianying.com (type=image)..." : "Already on target page: " + result.data.url;
    }
    case "s2_tab": {
      const result = await window.stepTab();
      if (!result.ok) return "ERROR: " + result.error;
      return "OK: Tab ready - " + JSON.stringify(result.data);
    }
    case "s3_model": {
      const result = await window.stepModel();
      if (!result.ok) return "ERROR: " + result.error;
      return "OK: Model changed to " + result.data.modelText;
    }
    case "s4_ratio": {
      const result = await window.stepRatio();
      if (!result.ok) return "ERROR: " + result.error;
      return "OK: Ratio 9:16 selected" + (result.data.resolution ? ", Res 2K" : "");
    }
    case "s5_upload": {
      // S5 test — check UI elements are present (full flow uses job.assets)
      const fileInputs = () => Array.from(document.querySelectorAll("input[type='file']"));
      const uploadSlots = Array.from(document.querySelectorAll("[data-testid*='upload'], [class*='upload'], [class*='Upload']")).filter(isVisible);
      const inputs = fileInputs();
      if (inputs.length > 0 || uploadSlots.length > 0) {
        return `OK: Upload UI present (${inputs.length} file inputs, ${uploadSlots.length} slots). Full flow uses job assets.`;
      }
      return "WARN: No upload UI found";
    }
    case "s6_prompt": {
      // S6 test — check prompt input is present
      const candidates = Array.from(document.querySelectorAll("textarea, input[placeholder*='描述'], div[contenteditable='true'], div.tiptap"));
      const visible = candidates.filter(el => el.getAttribute("contenteditable") === "true" || isVisible(el));
      if (visible.length > 0) return "OK: Prompt input found (" + visible.length + " elements). Full flow uses job.prompt.";
      return "WARN: No prompt input found";
    }
    case "s7_generate": {
      const result = await window.stepGenerate();
      if (!result.ok) return "ERROR: " + result.error;
      return "OK: Clicked 生成 button. count=" + result.data.count;
    }
    case "s8_wait": {
      const result = await window.stepWait({ timeoutSeconds: 600 });
      if (!result.ok) return "ERROR: " + result.error;
      window.__testResultImages = result.data.images;
      return "OK: Found " + result.data.images.length + " stable image(s). Ready for S9.";
    }
    case "s9_report": {
      const imgs = window.__testResultImages || [];
      if (imgs.length === 0) return "ERROR: No images from S8. Run S8_wait first.";
      const serialized = [];
      for (let i = 0; i < Math.min(imgs.length, 4); i++) {
        const img = imgs[i];
        try {
          const resp = await fetch(img.src, { credentials: "include" });
          if (!resp.ok) continue;
          const blob = await resp.blob();
          const mimeType = blob.type || "image/png";
          const reader = new FileReader();
          const base64 = await new Promise((resolve, reject) => {
            reader.onloadend = () => {
              const result = String(reader.result || "");
              const idx = result.indexOf(",");
              resolve(idx >= 0 ? result.slice(idx + 1) : result);
            };
            reader.onerror = reject;
            reader.readAsDataURL(blob);
          });
          const ext = ({ "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp" })[mimeType] || ".png";
          serialized.push({
            filename: `result-${String(i + 1).padStart(2, "0")}${ext}`,
            mimeType,
            base64Data: base64,
            sourceUrl: img.src,
          });
        } catch (err) {
          return `ERROR: Failed to serialize image ${i + 1}: ${err.message}`;
        }
      }

      if (serialized.length === 0) {
        return "ERROR: No images could be serialized";
      }

      // For test: just return the serialized result (no real job id to post to)
      window.__testSerializedImages = serialized;
      return `OK: Serialized ${serialized.length} image(s). ` +
        `First: ${serialized[0].filename} (${serialized[0].mimeType}, ${(serialized[0].base64Data.length / 1024).toFixed(1)}KB)`;
    }
    default:
      return "ERROR: Unknown step: " + step;
  }
}
