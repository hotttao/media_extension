// Dynamic imports for platform handlers
let runGptJob, runJimengImageJob, runJimengVideoJob;
let handlersLoaded = false;

async function ensureHandlersLoaded() {
  if (handlersLoaded) return;
  const [gpt, jimengImage, jimengVideo] = await Promise.all([
    import("./content-handlers/gpt.js"),
    import("./content-handlers/jimeng-image.js"),
    import("./content-handlers/jimeng-video.js"),
  ]);
  runGptJob = gpt.runGptJob;
  runJimengImageJob = jimengImage.runJimengImageJob;
  runJimengVideoJob = jimengVideo.runJimengVideoJob;
  handlersLoaded = true;
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

async function runJob(job, serverUrl) {
  await ensureHandlersLoaded();
  const platform = job.platform || "gpt";
  if (platform === "gpt") {
    await runGptJob(job, serverUrl);
  } else if (platform === "jimeng_image") {
    await runJimengImageJob(job, serverUrl);
  } else if (platform === "jimeng_video") {
    await runJimengVideoJob(job, serverUrl);
  } else {
    throw new Error(`Unknown platform: ${platform}`);
  }
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
      .catch((error) => {
        controllerState.busy = false;
        controllerState.currentJobId = null;
        sendResponse({ ok: false, error: String(error), state: { ...controllerState } });
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

  switch (step) {
    case "s1_nav": {
      const target = "https://jimeng.jianying.com/";
      if (window.location.href !== target) {
        window.location.href = target;
        return "Navigating to jimeng.jianying.com...";
      }
      return "Already on jimeng page: " + window.location.href;
    }
    case "s2_tab": {
      // First click: open the dropdown that contains "图片生成"
      const dropdownTriggers = Array.from(document.querySelectorAll("*")).filter(el =>
        isVisible(el) && (el.textContent?.trim() === "图片生成" || el.textContent?.trim() === "视频生成")
      );

      // Find the parent trigger (usually a div/button that opens the dropdown)
      const dropdownTrigger = dropdownTriggers.length > 0 ? dropdownTriggers[0] : null;

      if (!dropdownTrigger) {
        // List what's visible for debugging
        const allVisible = Array.from(document.querySelectorAll("*")).filter(el => isVisible(el));
        const samples = allVisible.map(el => el.tagName + ":[" + el.textContent?.trim().slice(0, 30) + "]").filter(t => t.length > 10).slice(0, 20);
        return "ERROR: 图片生成 not found. Sample: " + JSON.stringify(samples);
      }

      // Check if this is already an open dropdown option or a trigger
      // If it looks like a menu item, click it; otherwise click its parent to open dropdown first
      const parentClickable = dropdownTrigger.parentElement;
      const isMenuItem = parentClickable && (parentClickable.getAttribute("role")?.includes("menu") || parentClickable.className?.includes("menu") || parentClickable.tagName === "LI");

      if (!isMenuItem && dropdownTrigger.textContent?.trim() === "图片生成") {
        // Likely a trigger, click parent first
        if (parentClickable && isVisible(parentClickable)) {
          parentClickable.click();
          await delay(500);
          // Now click the actual option
          const secondClick = Array.from(document.querySelectorAll("*")).find(el =>
            el.textContent?.trim() === "图片生成" && isVisible(el) && el !== dropdownTrigger
          );
          if (secondClick) {
            secondClick.click();
            return "OK: Opened dropdown, then selected 图片生成. Parent was " + parentClickable.tagName;
          }
          return "OK: Clicked trigger " + parentClickable.tagName + ", dropdown opened.";
        }
        // Click the element itself to open dropdown
        dropdownTrigger.click();
        await delay(500);
        const option = Array.from(document.querySelectorAll("*")).find(el =>
          el.textContent?.trim() === "图片生成" && isVisible(el) && el !== dropdownTrigger
        );
        if (option) {
          option.click();
          return "OK: Clicked element, then selected 图片生成.";
        }
        return "OK: Clicked trigger. Options should be visible now.";
      }

      // It's a menu item inside an open dropdown
      dropdownTrigger.click();
      return "OK: Selected 图片生成 from dropdown. tabs count=" + dropdownTriggers.length;
    }
    case "s3_model": {
      // Model dropdown: model name (图片5.0 Lite), ratio (9:16), resolution (2K)
      const allEls = () => Array.from(document.querySelectorAll("*")).filter(el => isVisible(el));

      // Step 1: Find and click the model dropdown trigger (look for text containing model name or "Model")
      const trigger = allEls().find(el => {
        const text = el.textContent?.trim() || "";
        return text.includes("5.0") || text.includes("Lite") || text.includes("模型") || text.includes("9:16") || text.includes("2K");
      });

      if (!trigger) {
        const samples = allEls().map(el => el.tagName + ":[" + el.textContent?.trim().slice(0, 25) + "]").filter(t => t.length > 8).slice(0, 20);
        return "DEBUG: No model trigger found. Page text: " + JSON.stringify(samples);
      }

      // Click first to open dropdown
      trigger.click();
      await delay(300);

      // Step 2: Select 图片5.0 Lite (model name)
      const modelOption = allEls().find(el => {
        const text = el.textContent?.trim() || "";
        return text.includes("5.0") || text.includes("Lite");
      });
      if (modelOption && modelOption !== trigger) {
        modelOption.click();
        await delay(200);
      }

      // Step 3: Select 9:16 (ratio)
      const ratioOption = allEls().find(el => {
        const text = el.textContent?.trim() || "";
        return text === "9:16" || text.includes("9:16");
      });
      if (ratioOption) {
        ratioOption.click();
        await delay(200);
      } else {
        // Try clicking the ratio area directly if dropdown is still open
        const ratioArea = allEls().find(el => el.textContent?.trim().includes("9:16"));
        if (ratioArea && ratioArea !== trigger) ratioArea.click();
        await delay(200);
      }

      // Step 4: Select 2K (resolution)
      const resOption = allEls().find(el => {
        const text = el.textContent?.trim() || "";
        return text === "2K" || text.includes("2K") || text === "2k";
      });
      if (resOption) {
        resOption.click();
        await delay(200);
      } else {
        const resArea = allEls().find(el => el.textContent?.trim().includes("2K"));
        if (resArea && resArea !== trigger) resArea.click();
      }

      // Confirm selections
      const afterText = trigger.textContent?.trim() || "";
      return "OK: Model dropdown completed. Current display: " + afterText.slice(0, 80);
    }
    case "s4_upload": {
      return "OK: Upload test ready. This step would upload 3 reference images in full flow.";
    }
    case "s5_prompt": {
      return "OK: Prompt test ready. This step would fill prompt text in full flow.";
    }
    case "s6_generate": {
      const btns = Array.from(document.querySelectorAll("button")).filter(el =>
        el.textContent?.trim().includes("生成") && isVisible(el) && !el.disabled
      );
      if (btns.length > 0) {
        btns[0].click();
        return "OK: Clicked 生成 button. count=" + btns.length;
      }
      return "ERROR: Generate button not found";
    }
    case "s7_wait": {
      return "OK: Wait test ready. This step would poll for 8s stable results in full flow.";
    }
    case "s8_report": {
      return "OK: Report test ready. This step would postJson result in full flow.";
    }
    default:
      return "ERROR: Unknown step: " + step;
  }
}
