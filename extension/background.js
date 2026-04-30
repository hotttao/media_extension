const DEFAULT_SERVER_URL = "http://127.0.0.1:8765";

const controllerState = {
  running: false,
  busy: false,
  serverUrl: DEFAULT_SERVER_URL,
  currentJobId: null,
  lastMessage: "Idle",
  lastError: null,
  currentTabId: null,
};

let controllerLoopRunning = false;
let stopRequested = false;

async function loadSettings() {
  const stored = await chrome.storage.local.get(["serverUrl"]);
  if (stored.serverUrl) {
    controllerState.serverUrl = stored.serverUrl;
  }
}

async function saveSettings() {
  await chrome.storage.local.set({ serverUrl: controllerState.serverUrl });
}

function broadcastState() {
  chrome.runtime.sendMessage({ type: "controllerState", state: controllerState }).catch(() => {});
}

function setStatus(message, error = null) {
  controllerState.lastMessage = message;
  controllerState.lastError = error;
  broadcastState();
}

async function claimJob() {
  const response = await fetch(`${controllerState.serverUrl}/v1/job/claim`, {
    headers: {
      "X-Worker-Id": `chrome-extension-${chrome.runtime.id}`,
    },
  });
  if (!response.ok) {
    throw new Error(`Claim job failed with ${response.status}`);
  }
  return response.json();
}

async function requeueJob(jobId) {
  const response = await fetch(`${controllerState.serverUrl}/v1/job/${encodeURIComponent(jobId)}/requeue`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({}),
  });
  if (!response.ok) {
    throw new Error(`Requeue job failed with ${response.status}`);
  }
  return response.json();
}

async function ensureContentScript(tabId) {
  try {
    await chrome.tabs.sendMessage(tabId, { type: "ping" });
    return;
  } catch (_error) {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content-script.js"],
    });
  }
}

function chatStartUrl() {
  return "https://chatgpt.com/images";
}

function jobDefaultUrl(job) {
  const platform = job.platform || "gpt";
  if (platform === "jimeng_image" || platform === "jimeng_video") {
    return "https://jimeng.jianying.com/";
  }
  return chatStartUrl();
}

function waitForTabComplete(tabId, timeoutMs = 30000) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error(`Timed out while waiting for tab ${tabId} to load`));
    }, timeoutMs);

    function listener(updatedTabId, changeInfo) {
      if (updatedTabId !== tabId || changeInfo.status !== "complete") {
        return;
      }
      clearTimeout(timeout);
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    }

    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function openJobTab(job) {
  const targetUrl = job.targetUrl || jobDefaultUrl(job);
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

const JOB_RUN_TIMEOUT_MS = 10 * 60 * 1000; // 10 minutes per job

async function runJobInFreshTab(job) {
  let tabId = null;
  let windowId = null;
  let jobTimedOut = false;

  try {
    const freshTarget = await openJobTab(job);
    tabId = freshTarget.tabId;
    windowId = freshTarget.windowId;
    controllerState.currentTabId = tabId;
    controllerState.currentJobId = job.id;
    controllerState.busy = true;
    setStatus(`Running ${job.id}`);

    // Send job with timeout wrapper
    const sendJobWithTimeout = new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        jobTimedOut = true;
        reject(new Error(`Job ${job.id} timed out after ${JOB_RUN_TIMEOUT_MS / 1000}s`));
      }, JOB_RUN_TIMEOUT_MS);

      chrome.tabs.sendMessage(tabId, {
        type: "controller:runSingleJob",
        serverUrl: controllerState.serverUrl,
        job,
      }).then(resolve).catch(reject).finally(() => clearTimeout(timeout));
    });

    await sendJobWithTimeout;
  } finally {
    if (windowId !== null) {
      await chrome.windows.remove(windowId).catch(() => {});
    } else if (tabId !== null) {
      await chrome.tabs.remove(tabId).catch(() => {});
    }
    controllerState.busy = false;
    controllerState.currentJobId = null;
    controllerState.currentTabId = null;
    broadcastState();
  }
}

async function runControllerLoop() {
  if (controllerLoopRunning) {
    return;
  }

  controllerLoopRunning = true;
  stopRequested = false;
  try {
    while (controllerState.running && !stopRequested) {
      const payload = await claimJob();
      if (!payload.job) {
        setStatus("No pending jobs");
        await new Promise((resolve) => setTimeout(resolve, 5000));
        continue;
      }

      try {
        await runJobInFreshTab(payload.job);
      } catch (error) {
        const reason = error instanceof Error ? error.message : String(error);
        try {
          await requeueJob(payload.job.id);
          setStatus(`Requeued ${payload.job.id}`, reason);
        } catch (_requeueError) {
          setStatus(`Failed ${payload.job.id}`, reason);
        }
      }
    }
  } finally {
    controllerLoopRunning = false;
    controllerState.busy = false;
    controllerState.currentJobId = null;
    broadcastState();
  }
}

async function startController(serverUrl) {
  controllerState.serverUrl = (serverUrl || DEFAULT_SERVER_URL).trim() || DEFAULT_SERVER_URL;
  await saveSettings();

  controllerState.running = true;
  controllerState.busy = false;
  controllerState.currentJobId = null;
  setStatus("Controller started");
  runControllerLoop().catch((error) => {
    controllerState.running = false;
    setStatus("Controller failed", String(error));
  });
}

async function stopController() {
  stopRequested = true;
  controllerState.running = false;
  controllerState.busy = false;
  controllerState.currentJobId = null;
  setStatus("Controller stopped");
}

async function syncStateFromTab() {
  return controllerState;
}

async function bridgeFetch({ url, method = "GET", headers = {}, body = null, responseType = "json" }) {
  const response = await fetch(url, {
    method,
    headers,
    body: body == null ? null : JSON.stringify(body),
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => "");
    throw new Error(`Fetch failed with ${response.status}${errorText ? `: ${errorText}` : ""}`);
  }

  if (responseType === "blobBase64") {
    const blob = await response.blob();
    const buffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    let binary = "";
    const chunkSize = 0x8000;
    for (let index = 0; index < bytes.length; index += chunkSize) {
      const chunk = bytes.subarray(index, index + chunkSize);
      binary += String.fromCharCode(...chunk);
    }
    return {
      ok: true,
      mimeType: blob.type || response.headers.get("Content-Type") || "application/octet-stream",
      base64Data: btoa(binary),
    };
  }

  if (responseType === "text") {
    return {
      ok: true,
      text: await response.text(),
    };
  }

  return {
    ok: true,
    json: await response.json(),
  };
}

chrome.runtime.onInstalled.addListener(() => {
  loadSettings().then(broadcastState);
});

chrome.runtime.onStartup.addListener(() => {
  loadSettings().then(broadcastState);
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "popup:getState") {
    syncStateFromTab()
      .then((state) => sendResponse({ state }))
      .catch(() => sendResponse({ state: controllerState }));
    return true;
  }

  if (message?.type === "popup:start") {
    startController(message.serverUrl)
      .then(() => sendResponse({ ok: true, state: controllerState }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  if (message?.type === "popup:stop") {
    stopController()
      .then(() => sendResponse({ ok: true, state: controllerState }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  if (message?.type === "content:progress") {
    controllerState.running = message.state?.running ?? controllerState.running;
    controllerState.busy = message.state?.busy ?? controllerState.busy;
    controllerState.currentJobId = message.state?.currentJobId ?? controllerState.currentJobId;
    controllerState.serverUrl = message.state?.serverUrl || controllerState.serverUrl;
    setStatus(message.message || "Working", message.state?.lastError || null);
    sendResponse({ ok: true });
    return true;
  }

  if (message?.type === "content:finished") {
    controllerState.running = message.state?.running ?? true;
    controllerState.busy = false;
    controllerState.currentJobId = null;
    setStatus(`Completed ${message.jobId}`, null);
    sendResponse({ ok: true });
    return true;
  }

  if (message?.type === "content:failed") {
    controllerState.running = message.state?.running ?? true;
    controllerState.busy = false;
    controllerState.currentJobId = null;
    setStatus(`Failed ${message.jobId}`, message.reason || "Unknown error");
    sendResponse({ ok: true });
    return true;
  }

  if (message?.type === "content:requeued") {
    controllerState.running = message.state?.running ?? false;
    controllerState.busy = false;
    controllerState.currentJobId = null;
    setStatus(message.message || "Job requeued", message.reason || null);
    sendResponse({ ok: true });
    return true;
  }

  if (message?.type === "bridge:fetch") {
    bridgeFetch(message.request)
      .then((payload) => sendResponse(payload))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  if (message?.type === "popup:cancelAll") {
    const { platform } = message;
    fetch(`${controllerState.serverUrl}/v1/jobs/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ platform }),
    })
      .then((resp) => resp.json())
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  if (message?.type === "test:step") {
    const { platform, step } = message;
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs.length === 0 || !tabs[0].id) {
        sendResponse({ ok: false, error: "No active tab found" });
        return;
      }
      chrome.tabs.sendMessage(tabs[0].id, { type: "test:step", platform, step }, (resp) => {
        if (chrome.runtime.lastError) {
          sendResponse({ ok: false, error: chrome.runtime.lastError.message });
        } else {
          sendResponse(resp || { ok: false, error: "No response from content script" });
        }
      });
    });
    return true;
  }
});

loadSettings().then(broadcastState);
