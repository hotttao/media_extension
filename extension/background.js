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

async function findChatTab() {
  const tabs = await chrome.tabs.query({});
  const candidates = tabs.filter((tab) => {
    return typeof tab.url === "string" && (tab.url.startsWith("https://chatgpt.com/") || tab.url.startsWith("https://chat.openai.com/"));
  });

  const activeCandidate = candidates.find((tab) => tab.active);
  return activeCandidate || candidates[0] || null;
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

async function startController(serverUrl) {
  controllerState.serverUrl = (serverUrl || DEFAULT_SERVER_URL).trim() || DEFAULT_SERVER_URL;
  await saveSettings();

  const tab = await findChatTab();
  if (!tab?.id) {
    setStatus("Open a logged-in ChatGPT tab first");
    return;
  }

  controllerState.currentTabId = tab.id;

  try {
    await ensureContentScript(tab.id);
    const response = await chrome.tabs.sendMessage(tab.id, {
      type: "controller:start",
      serverUrl: controllerState.serverUrl,
    });
    controllerState.running = true;
    controllerState.busy = response?.state?.busy ?? false;
    controllerState.currentJobId = response?.state?.currentJobId ?? null;
    setStatus(response?.state?.lastMessage || "Controller started", response?.state?.lastError || null);
  } catch (error) {
    setStatus("Failed to start page automation", String(error));
  }
}

async function stopController() {
  const tab = await findChatTab();
  if (tab?.id) {
    try {
      await ensureContentScript(tab.id);
      await chrome.tabs.sendMessage(tab.id, { type: "controller:stop" });
    } catch (_error) {
      // Ignore and still reset UI state.
    }
  }

  controllerState.running = false;
  controllerState.busy = false;
  controllerState.currentJobId = null;
  setStatus("Controller stopped");
}

async function syncStateFromTab() {
  const tab = await findChatTab();
  if (!tab?.id) {
    controllerState.currentTabId = null;
    return controllerState;
  }

  controllerState.currentTabId = tab.id;

  try {
    await ensureContentScript(tab.id);
    const response = await chrome.tabs.sendMessage(tab.id, { type: "controller:getState" });
    if (response?.state) {
      controllerState.running = response.state.running;
      controllerState.busy = response.state.busy;
      controllerState.currentJobId = response.state.currentJobId;
      controllerState.serverUrl = response.state.serverUrl || controllerState.serverUrl;
      controllerState.lastMessage = response.state.lastMessage || controllerState.lastMessage;
      controllerState.lastError = response.state.lastError || null;
    }
  } catch (_error) {
    // Keep last known state if the page cannot respond.
  }

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

  return false;
});

loadSettings().then(broadcastState);
