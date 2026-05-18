const DEFAULT_SERVER_URL = "http://127.0.0.1:8765";
const DASHBOARD_URL = chrome.runtime.getURL("dashboard.html");
const USER_ABORTED_VIDEO_GENERATE_CONFIRMATION = "USER_ABORTED_VIDEO_GENERATE_CONFIRMATION";

const PLATFORM_DEFS = [
  { id: "gpt-image", name: "ChatGPT 图片", defaultIntervalSeconds: 3, defaultConcurrency: 1 },
  { id: "jimeng-image", name: "即梦图片", defaultIntervalSeconds: 5, defaultConcurrency: 1 },
  { id: "jimeng-video", name: "即梦视频", defaultIntervalSeconds: 10, defaultConcurrency: 1 },
];

const PLATFORM_IDS = PLATFORM_DEFS.map((platform) => platform.id);

function createPlatformState(platform) {
  return {
    id: platform.id,
    name: platform.name,
    running: false,
    busyCount: 0,
    pendingCount: 0,
    runningCount: 0,
    currentJobIds: [],
    currentJobId: null,
    lastMessage: "Idle",
    lastError: null,
    intervalSeconds: platform.defaultIntervalSeconds,
    concurrency: platform.defaultConcurrency,
  };
}

const controllerState = {
  serverUrl: DEFAULT_SERVER_URL,
  confirmBeforeVideoGenerate: false,
  dashboardWindowId: null,
  lastUpdatedAt: null,
  platforms: Object.fromEntries(PLATFORM_DEFS.map((platform) => [platform.id, createPlatformState(platform)])),
};

const activeJobs = new Map();
const loopRunning = Object.fromEntries(PLATFORM_IDS.map((platformId) => [platformId, false]));

function platformById(platformId) {
  return controllerState.platforms[platformId];
}

function cloneState() {
  return {
    serverUrl: controllerState.serverUrl,
    confirmBeforeVideoGenerate: controllerState.confirmBeforeVideoGenerate,
    dashboardWindowId: controllerState.dashboardWindowId,
    lastUpdatedAt: controllerState.lastUpdatedAt,
    platforms: Object.fromEntries(PLATFORM_IDS.map((platformId) => {
      const state = platformById(platformId);
      return [platformId, { ...state, currentJobIds: [...state.currentJobIds] }];
    })),
  };
}

async function loadSettings() {
  const stored = await chrome.storage.local.get(["serverUrl", "confirmBeforeVideoGenerate", "platformSettings"]);
  if (stored.serverUrl) {
    controllerState.serverUrl = stored.serverUrl;
  }
  if (typeof stored.confirmBeforeVideoGenerate === "boolean") {
    controllerState.confirmBeforeVideoGenerate = stored.confirmBeforeVideoGenerate;
  }
  const settings = stored.platformSettings || {};
  for (const platform of PLATFORM_DEFS) {
    const target = platformById(platform.id);
    const persisted = settings[platform.id] || {};
    if (typeof persisted.intervalSeconds === "number") {
      target.intervalSeconds = Math.max(1, Math.floor(persisted.intervalSeconds));
    }
    if (typeof persisted.concurrency === "number") {
      target.concurrency = Math.max(1, Math.floor(persisted.concurrency));
    }
  }
}

async function saveSettings() {
  const platformSettings = Object.fromEntries(PLATFORM_IDS.map((platformId) => {
    const state = platformById(platformId);
    return [platformId, {
      intervalSeconds: state.intervalSeconds,
      concurrency: state.concurrency,
    }];
  }));
  await chrome.storage.local.set({
    serverUrl: controllerState.serverUrl,
    confirmBeforeVideoGenerate: controllerState.confirmBeforeVideoGenerate,
    platformSettings,
  });
}

function broadcastState() {
  chrome.runtime.sendMessage({ type: "dashboard:state", state: cloneState() }).catch(() => {});
}

function classifyPlatform(job) {
  if (!job) return "gpt-image";
  if (job.platformId) return job.platformId;
  if (job.platform === "jimeng") {
    return job.targetUrl && job.targetUrl.includes("type=video") ? "jimeng-video" : "jimeng-image";
  }
  if (job.mediaAi?.kind === "video") return "jimeng-video";
  if (job.mediaAi?.platform === "jimeng") return "jimeng-image";
  return "gpt-image";
}

function setPlatformStatus(platformId, message, error = null) {
  const state = platformById(platformId);
  state.lastMessage = message;
  state.lastError = error;
  broadcastState();
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function claimJob(platformId) {
  const response = await fetch(`${controllerState.serverUrl}/v1/job/claim?platform=${encodeURIComponent(platformId)}`, {
    headers: {
      "X-Worker-Id": `chrome-extension-${chrome.runtime.id}:${platformId}`,
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
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!response.ok) {
    throw new Error(`Requeue job failed with ${response.status}`);
  }
  return response.json();
}

async function refreshQueueState() {
  try {
    const response = await fetch(`${controllerState.serverUrl}/v1/state`);
    if (!response.ok) {
      throw new Error(`State fetch failed with ${response.status}`);
    }
    const payload = await response.json();
    const jobs = payload.jobs || [];
    for (const platformId of PLATFORM_IDS) {
      const platformJobs = jobs.filter((job) => classifyPlatform(job) === platformId);
      const state = platformById(platformId);
      state.pendingCount = platformJobs.filter((job) => job.status === "pending").length;
      state.runningCount = platformJobs.filter((job) => job.status === "running").length;
    }
    controllerState.lastUpdatedAt = new Date().toISOString();
    broadcastState();
    return jobs;
  } catch (error) {
    for (const platformId of PLATFORM_IDS) {
      if (!platformById(platformId).lastError) {
        platformById(platformId).lastError = String(error);
      }
    }
    broadcastState();
    return [];
  }
}

async function ensureContentScript(tabId) {
  try {
    await chrome.tabs.sendMessage(tabId, { type: "ping" });
  } catch (_error) {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content-script.js"],
    });
  }
}

function jobDefaultUrl(job) {
  const platformId = classifyPlatform(job);
  if (platformId === "jimeng-image" || platformId === "jimeng-video") {
    return "https://jimeng.jianying.com/";
  }
  return "https://chatgpt.com/images";
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
    width: 650,
    height: 350,
  });
  const tab = createdWindow.tabs?.[0];
  if (!createdWindow.id || !tab?.id) {
    throw new Error("Failed to create window");
  }
  await waitForTabComplete(tab.id);
  await ensureContentScript(tab.id);
  return { tabId: tab.id, windowId: createdWindow.id };
}

const JOB_RUN_TIMEOUT_MS = 10 * 60 * 1000;

async function runJobInFreshTab(job, platformId) {
  let tabId = null;
  let windowId = null;
  const effectiveJob = platformId === "jimeng-video"
    ? { ...job, confirmBeforeVideoGenerate: controllerState.confirmBeforeVideoGenerate }
    : job;

  try {
    const freshTarget = await openJobTab(effectiveJob);
    tabId = freshTarget.tabId;
    windowId = freshTarget.windowId;

    const sendJobWithTimeout = new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error(`Job ${effectiveJob.id} timed out after ${JOB_RUN_TIMEOUT_MS / 1000}s`));
      }, JOB_RUN_TIMEOUT_MS);

      chrome.tabs.sendMessage(tabId, {
        type: "controller:runSingleJob",
        serverUrl: controllerState.serverUrl,
        job: effectiveJob,
      }).then((response) => {
        clearTimeout(timeout);
        if (response && response.ok === false) {
          reject(new Error(response.error || "Job failed"));
        } else {
          resolve(response);
        }
      }).catch((error) => {
        clearTimeout(timeout);
        reject(error);
      });
    });

    await sendJobWithTimeout;
  } finally {
    console.log("[runJobInFreshTab] leaving page open for debugging, tab:", tabId, "window:", windowId);
  }
}

async function launchJob(platformId, job) {
  const state = platformById(platformId);
  state.busyCount += 1;
  state.currentJobIds.push(job.id);
  state.currentJobId = state.currentJobIds[0] || null;
  state.lastError = null;
  state.lastMessage = `Running ${job.id}`;
  activeJobs.set(job.id, platformId);
  broadcastState();

  try {
    await runJobInFreshTab(job, platformId);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    if (reason.includes(USER_ABORTED_VIDEO_GENERATE_CONFIRMATION)) {
      setPlatformStatus(platformId, `Aborted ${job.id}`, "Video submission canceled before generate");
    } else {
      try {
        await requeueJob(job.id);
        setPlatformStatus(platformId, `Requeued ${job.id}`, reason);
      } catch (_requeueError) {
        setPlatformStatus(platformId, `Failed ${job.id}`, reason);
      }
    }
  } finally {
    state.busyCount = Math.max(0, state.busyCount - 1);
    state.currentJobIds = state.currentJobIds.filter((jobId) => jobId !== job.id);
    state.currentJobId = state.currentJobIds[0] || null;
    activeJobs.delete(job.id);
    await refreshQueueState();
    if (state.running) {
      ensurePlatformLoop(platformId).catch((error) => {
        setPlatformStatus(platformId, "Loop failed", String(error));
      });
    }
  }
}

async function ensurePlatformLoop(platformId) {
  if (loopRunning[platformId]) {
    return;
  }

  loopRunning[platformId] = true;
  try {
    while (platformById(platformId).running) {
      const state = platformById(platformId);
      if (state.busyCount >= state.concurrency) {
        await delay(500);
        continue;
      }

      let payload = null;
      try {
        payload = await claimJob(platformId);
      } catch (error) {
        setPlatformStatus(platformId, "Claim failed", String(error));
        await delay(state.intervalSeconds * 1000);
        continue;
      }

      if (payload?.job) {
        launchJob(platformId, payload.job).catch((error) => {
          setPlatformStatus(platformId, "Launch failed", String(error));
        });
      } else {
        state.lastMessage = "No pending jobs";
      }

      await refreshQueueState();
      await delay(state.intervalSeconds * 1000);
    }
  } finally {
    loopRunning[platformId] = false;
    broadcastState();
  }
}

async function startPlatform(platformId) {
  const state = platformById(platformId);
  state.running = true;
  state.lastError = null;
  state.lastMessage = "Controller started";
  broadcastState();
  await refreshQueueState();
  ensurePlatformLoop(platformId).catch((error) => {
    setPlatformStatus(platformId, "Loop failed", String(error));
  });
}

async function stopPlatform(platformId) {
  const state = platformById(platformId);
  state.running = false;
  state.lastMessage = "Controller stopped";
  broadcastState();
}

async function startAllPlatforms() {
  for (const platformId of PLATFORM_IDS) {
    await startPlatform(platformId);
  }
}

async function stopAllPlatforms() {
  for (const platformId of PLATFORM_IDS) {
    await stopPlatform(platformId);
  }
}

async function cancelAllPlatforms() {
  for (const platformId of PLATFORM_IDS) {
    await cancelPlatform(platformId);
  }
}

async function cancelPlatform(platformId) {
  const response = await fetch(`${controllerState.serverUrl}/v1/jobs/cancel?platform=${encodeURIComponent(platformId)}`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(`Cancel failed with ${response.status}`);
  }
  const result = await response.json();
  await refreshQueueState();
  return result;
}

async function updatePlatformSettings(platformId, settings) {
  const state = platformById(platformId);
  if (typeof settings.intervalSeconds === "number") {
    state.intervalSeconds = Math.max(1, Math.floor(settings.intervalSeconds));
  }
  if (typeof settings.concurrency === "number") {
    state.concurrency = Math.max(1, Math.floor(settings.concurrency));
  }
  await saveSettings();
  broadcastState();
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
    return { ok: true, text: await response.text() };
  }

  return { ok: true, json: await response.json() };
}

async function openDashboardWindow() {
  if (controllerState.dashboardWindowId !== null) {
    try {
      const existing = await chrome.windows.get(controllerState.dashboardWindowId);
      if (existing?.id) {
        await chrome.windows.update(existing.id, { focused: true });
        return existing.id;
      }
    } catch (_error) {
      controllerState.dashboardWindowId = null;
    }
  }

  const created = await chrome.windows.create({
    url: DASHBOARD_URL,
    type: "popup",
    width: 800,
    height: 720,
    focused: true,
  });
  controllerState.dashboardWindowId = created.id ?? null;
  broadcastState();
  return controllerState.dashboardWindowId;
}

chrome.action.onClicked.addListener(() => {
  openDashboardWindow().catch(() => {});
});

chrome.windows.onRemoved.addListener((windowId) => {
  if (controllerState.dashboardWindowId === windowId) {
    controllerState.dashboardWindowId = null;
    broadcastState();
  }
});

chrome.runtime.onInstalled.addListener(() => {
  loadSettings().then(() => refreshQueueState()).catch(() => broadcastState());
});

chrome.runtime.onStartup.addListener(() => {
  loadSettings().then(() => refreshQueueState()).catch(() => broadcastState());
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "dashboard:getState") {
    refreshQueueState()
      .then(() => sendResponse({ ok: true, state: cloneState() }))
      .catch(() => sendResponse({ ok: true, state: cloneState() }));
    return true;
  }

  if (message?.type === "dashboard:open") {
    openDashboardWindow()
      .then(() => sendResponse({ ok: true, state: cloneState() }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  if (message?.type === "dashboard:updateGlobalSettings") {
    if (typeof message.serverUrl === "string") {
      controllerState.serverUrl = message.serverUrl.trim() || DEFAULT_SERVER_URL;
    }
    if (typeof message.confirmBeforeVideoGenerate === "boolean") {
      controllerState.confirmBeforeVideoGenerate = message.confirmBeforeVideoGenerate;
    }
    saveSettings()
      .then(() => refreshQueueState())
      .then(() => sendResponse({ ok: true, state: cloneState() }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  if (message?.type === "dashboard:updatePlatformSettings") {
    updatePlatformSettings(message.platformId, message.settings || {})
      .then(() => sendResponse({ ok: true, state: cloneState() }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  if (message?.type === "dashboard:startPlatform") {
    startPlatform(message.platformId)
      .then(() => sendResponse({ ok: true, state: cloneState() }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  if (message?.type === "dashboard:startAllPlatforms") {
    startAllPlatforms()
      .then(() => sendResponse({ ok: true, state: cloneState() }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  if (message?.type === "dashboard:stopPlatform") {
    stopPlatform(message.platformId)
      .then(() => sendResponse({ ok: true, state: cloneState() }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  if (message?.type === "dashboard:stopAllPlatforms") {
    stopAllPlatforms()
      .then(() => sendResponse({ ok: true, state: cloneState() }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  if (message?.type === "dashboard:cancelPlatform") {
    cancelPlatform(message.platformId)
      .then((result) => sendResponse({ ok: true, result, state: cloneState() }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  if (message?.type === "dashboard:cancelAllPlatforms") {
    cancelAllPlatforms()
      .then(() => sendResponse({ ok: true, state: cloneState() }))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  if (message?.type === "content:progress") {
    const platformId = activeJobs.get(message.state?.currentJobId) || activeJobs.get(message.jobId) || "gpt-image";
    setPlatformStatus(platformId, message.message || "Working", message.state?.lastError || null);
    sendResponse({ ok: true });
    return true;
  }

  if (message?.type === "content:finished") {
    const platformId = activeJobs.get(message.jobId) || "gpt-image";
    setPlatformStatus(platformId, `Completed ${message.jobId}`, null);
    sendResponse({ ok: true });
    return true;
  }

  if (message?.type === "content:failed") {
    const platformId = activeJobs.get(message.jobId) || "gpt-image";
    setPlatformStatus(platformId, `Failed ${message.jobId}`, message.reason || "Unknown error");
    sendResponse({ ok: true });
    return true;
  }

  if (message?.type === "bridge:fetch") {
    bridgeFetch(message.request)
      .then((payload) => sendResponse(payload))
      .catch((error) => sendResponse({ ok: false, error: String(error) }));
    return true;
  }

  if (message?.type === "test:step") {
    const { platform, step } = message;
    if (step === "s1_nav") {
      const targetUrl = platform === "jimeng" || platform === "jimeng-video"
        ? "https://jimeng.jianying.com/"
        : "https://chatgpt.com/images";
      chrome.tabs.create({ url: targetUrl, active: true }, (tab) => {
        if (chrome.runtime.lastError) {
          sendResponse({ ok: false, error: chrome.runtime.lastError.message });
        } else {
          sendResponse({ ok: true, result: "Opening " + targetUrl + " tabId=" + tab.id });
        }
      });
      return true;
    }

    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs.length === 0 || !tabs[0].id) {
        sendResponse({ ok: false, error: "No active tab found" });
        return;
      }
      chrome.tabs.sendMessage(tabs[0].id, { type: "test:step", platform, step }, (resp) => {
        if (chrome.runtime.lastError) {
          sendResponse({ ok: false, error: "Content script not loaded: " + chrome.runtime.lastError.message + ". Make sure you're on the target page." });
        } else {
          sendResponse(resp || { ok: false, error: "No response from content script" });
        }
      });
    });
    return true;
  }
});

loadSettings().then(() => refreshQueueState()).catch(() => broadcastState());
