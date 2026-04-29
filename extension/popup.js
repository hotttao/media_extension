const PLATFORMS = [
  { id: "gpt", name: "ChatGPT 图片" },
  { id: "jimeng_image", name: "即梦图片" },
  { id: "jimeng_video", name: "即梦视频" },
];

const controllerState = {};

function renderPlatformSection(platform) {
  const state = controllerState[platform.id] || {
    running: false,
    busy: false,
    lastMessage: "Idle",
    currentJobId: null,
    lastError: null,
  };

  return `
    <div class="platform-section" data-platform="${platform.id}">
      <div class="platform-header">${platform.name}</div>
      <div class="platform-body">
        <div class="actions">
          <button class="start-btn" data-platform="${platform.id}" ${state.busy ? "disabled" : ""}>Start</button>
          <button class="stop-btn" data-platform="${platform.id}" ${!state.running ? "disabled" : ""}>Stop</button>
          <button class="cancel-btn danger" data-platform="${platform.id}" ${!state.running ? "disabled" : ""}>Cancel All</button>
        </div>
        <div class="stats">
          <div class="stat-item">
            <span class="stat-label">Job:</span>
            <span class="job-id">${state.currentJobId || "-"}</span>
          </div>
        </div>
        <div class="status-line">${state.lastMessage || "Idle"}</div>
        <div class="error-line">${state.lastError || ""}</div>
      </div>
    </div>
  `;
}

function render() {
  const container = document.getElementById("platforms");
  container.innerHTML = PLATFORMS.map(renderPlatformSection).join("");

  // Bind event listeners
  container.querySelectorAll(".start-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const platform = btn.dataset.platform;
      const response = await chrome.runtime.sendMessage({
        type: "popup:start",
        platform,
      });
      if (response?.state) {
        mergeState(response.state, platform);
        render();
      }
    });
  });

  container.querySelectorAll(".stop-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const platform = btn.dataset.platform;
      const response = await chrome.runtime.sendMessage({
        type: "popup:stop",
        platform,
      });
      if (response?.state) {
        mergeState(response.state, platform);
        render();
      }
    });
  });

  container.querySelectorAll(".cancel-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const platform = btn.dataset.platform;
      await chrome.runtime.sendMessage({
        type: "popup:cancelAll",
        platform,
      });
    });
  });
}

function mergeState(state, platform) {
  if (platform) {
    controllerState[platform] = state;
  } else if (state.platform) {
    controllerState[state.platform] = state;
  } else {
    Object.assign(controllerState, state);
  }
}

async function refresh() {
  const response = await chrome.runtime.sendMessage({ type: "popup:getState" });
  if (response?.state) {
    mergeState(response.state);
    render();
  }
}

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "controllerState") {
    mergeState(message.state);
    render();
  }
});

refresh();