const PLATFORMS = [
  { id: "gpt", name: "ChatGPT 图片" },
  { id: "jimeng_image", name: "即梦图片" },
  { id: "jimeng_video", name: "即梦视频" },
];

const TEST_STEPS = {
  jimeng_image: [
    { id: "s1_nav", label: "S1 导航" },
    { id: "s2_tab", label: "S2 Tab" },
    { id: "s3_model", label: "S3 模型" },
    { id: "s4_upload", label: "S4 上传" },
    { id: "s5_prompt", label: "S5 Prompt" },
    { id: "s6_generate", label: "S6 生成" },
    { id: "s7_wait", label: "S7 等待" },
    { id: "s8_report", label: "S8 上报" },
  ],
};

const controllerState = {};

function renderPlatformSection(platform) {
  const state = controllerState[platform.id] || {
    running: false,
    busy: false,
    lastMessage: "Idle",
    currentJobId: null,
    lastError: null,
  };

  const testSteps = TEST_STEPS[platform.id] || [];
  const testResultId = `test-result-${platform.id}`;
  const testResult = (controllerState[`${platform.id}_testResult`] || "");

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
        ${testSteps.length > 0 ? `
        <div class="test-panel">
          <div class="test-panel-label">Test Steps (on jimeng page)</div>
          <div class="test-steps">
            ${testSteps.map(step => `
              <button class="test-btn" data-platform="${platform.id}" data-step="${step.id}">${step.label}</button>
            `).join("")}
          </div>
          <div class="test-result ${testResult.startsWith('ERROR') ? 'error' : ''}" id="${testResultId}">${testResult || "Click a step to test..."}</div>
        </div>
        ` : ""}
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

  // Bind test step buttons
  container.querySelectorAll(".test-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const platform = btn.dataset.platform;
      const step = btn.dataset.step;
      btn.disabled = true;
      btn.textContent = "...";

      const resultEl = document.getElementById(`test-result-${platform}`);
      resultEl.textContent = "Running test step...";
      resultEl.className = "test-result";

      try {
        const response = await chrome.runtime.sendMessage({
          type: "test:step",
          platform,
          step,
        });
        const result = response?.result || response?.error || "No response";
        const isError = result.startsWith("ERROR");
        resultEl.textContent = result;
        resultEl.className = `test-result ${isError ? "error" : ""}`;
        controllerState[`${platform}_testResult`] = result;
      } catch (err) {
        resultEl.textContent = "ERROR: " + err.message;
        resultEl.className = "test-result error";
        controllerState[`${platform}_testResult`] = "ERROR: " + err.message;
      }

      btn.disabled = false;
      const stepBtn = Array.from(document.querySelectorAll(`.test-btn[data-platform="${platform}"]`)).find(b => b.dataset.step === step);
      if (stepBtn) stepBtn.textContent = step.replace("s", "S").replace("_", " ");
      // Restore label
      const originalLabel = TEST_STEPS[platform]?.find(s => s.id === step)?.label || step;
      btn.textContent = originalLabel;
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