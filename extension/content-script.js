const DEFAULT_TIMEOUT_MS = 15 * 60 * 1000;
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
  const timeoutMs = options.timeoutMs ?? 10000;
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
    timeoutMs: 5000,
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
    await delay(2500);
    return;
  }

  for (const file of files) {
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
    input.dispatchEvent(new Event("input", { bubbles: true }));
    await delay(1500);
  }
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
  const deadline = Date.now() + 10000;

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
    const composer = await waitFor(() => findComposer(), { timeoutMs: 15000, label: "prompt composer" });

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

  return false;
});
