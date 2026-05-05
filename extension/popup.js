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

  const testSteps = [];

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

  // Bind manual run button
  container.querySelectorAll(".manual-run-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const platform = btn.dataset.platform;
      const inputEl = document.getElementById(`manual-input-${platform}`);
      const resultEl = document.getElementById(`manual-result-${platform}`);
      
      btn.disabled = true;
      btn.textContent = "Running...";
      resultEl.textContent = "";
      resultEl.className = "manual-result";
      inputEl.classList.remove("error");

      try {
        let job;
        try {
          job = JSON.parse(raw);
        } catch (_e) {
          throw new Error("Invalid JSON: " + _e.message);
        }

        if (!job.id) throw new Error("job.id is required");

        // Detect bridge-format job (has mediaAi but no assets/prompt/targetUrl)
        const isBridgeFormat = job.mediaAi && !job.assets;
        let normalizedJob = job;

        if (isBridgeFormat) {
          const ma = job.mediaAi;
          // Build targetUrl from mediaAi kind
          const kind2url = {
            "jimeng-image": "https://jimeng.jianying.com/ai-tool/home/?type=image&workspace=0",
            "jimeng-video": "https://jimeng.jianying.com/ai-tool/home/?type=video&workspace=0",
          };
          const targetUrl = job.targetUrl || kind2url[ma.kind] || "https://jimeng.jianying.com/ai-tool/home/?type=image&workspace=0";

          // Build assets from mediaAi sidecar
          const assets = [];
          if (ma.styleImageUrl) {
            assets.push({
              url: ma.styleImageUrl,
              name: "styleImage.png",
              mimeType: "image/png",
            });
          }
          if (ma.sceneUrl) {
            assets.push({
              url: ma.sceneUrl,
              name: "scene.jpg",
              mimeType: "image/jpeg",
            });
          }

          // Construct normalized job for content handler
          normalizedJob = {
            id: job.id,
            platform: ma.kind === "jimeng-video" ? "jimeng_video" : "jimeng_image",
            targetUrl,
            prompt: ma.productName || "",
            assets,
            mediaAi: ma,
          };
        } else {
          // Fallback: require explicit targetUrl / platform
          if (!job.targetUrl && !job.platform) {
            throw new Error("job.targetUrl or job.platform is required");
          }
        }

        // Bypass dynamic import() entirely by inlining the handler.
        // The injected script sets up step functions + calls runJimengImageJob directly.
        const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!tab?.id) throw new Error("No active tab");

        // Inject jimeng-steps.js as a content script — chrome.runtime is available
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ["jimeng-steps.js"],
        });

        // Inject the inline runner (no dynamic import, chrome.runtime via executeScript)
        const serverUrl = "http://127.0.0.1:8765";
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          func: (job, su) => {
            // ── Inline helpers (mirrors jimeng-image.js) ──
            const delay = ms => new Promise(r => setTimeout(r, ms));
            const waitFor = (pred, opts = {}) => {
              const deadline = Date.now() + (opts.timeoutMs ?? 120000);
              while (Date.now() < deadline) { const v = pred(); if (v) return v; }
              throw new Error("Timed out: " + (opts.label || "condition"));
            };
            const bridgeFetch = req => chrome.runtime.sendMessage({ type: "bridge:fetch", request: req })
              .then(r => { if (!r.ok) throw new Error(r.error); return r; });
            const postJson = (url, payload) => bridgeFetch({ url, method: "POST", headers: { "Content-Type": "application/json" }, body: payload, responseType: "json" }).then(r => r.json);
            const blobToBase64 = blob => new Promise((res, rej) => {
              const fr = new FileReader();
              fr.onloadend = () => { const result = String(fr.result || ""); res(result.indexOf(",") >= 0 ? result.slice(result.indexOf(",") + 1) : result); };
              fr.onerror = rej;
              fr.readAsDataURL(blob);
            });

            const record = async (msg, details = null) => {
              const at = new Date().toISOString();
              window.postMessage({ type: "manual:job:log", message: msg, at, details }, "*");
            };

            const snapshotDOM = () => {
              try {
                const cbs = Array.from(document.querySelectorAll("[role=combobox]")).map(el => el.textContent.trim().slice(0, 60));
                const btns = Array.from(document.querySelectorAll("button")).filter(el => el.getBoundingClientRect().width > 0).map(el => el.textContent.trim().slice(0, 40));
                const inputs = document.querySelectorAll("input[type=file]").length;
                return JSON.stringify({ comboboxes: cbs, buttons: btns, fileInputs: inputs, url: window.location.href.slice(0, 80) });
              } catch { return "{}"; }
            };

            // ── Main handler (runJimengImageJob inlined) ──
            const logs = [];

            (async () => {
              try {
                await record("Preparing " + job.id);

                // S1: Navigate
                if (window.location.href !== job.targetUrl) {
                  await record("Navigating to Jimeng");
                  window.location.href = job.targetUrl;
                  await waitFor(() => window.location.href.includes("type=image"), { timeoutMs: 30000, label: "jimeng image page" });
                  await delay(2000);
                } else { await delay(1000); }

                // Wait for page ready
                await record("Waiting for page to be ready");
                try {
                  waitFor(() => document.querySelector("[role=combobox]"), { timeoutMs: 20000, label: "combobox" });
                  waitFor(() => document.querySelector("input[type=file]"), { timeoutMs: 10000, label: "file_input" });
                } catch (e) { throw new Error("Page not ready: " + e.message); }
                await delay(500);

                // S3: Select model
                await record("Selecting model 图片5.0 Lite");
                const modelResult = await window.stepModel();
                if (!modelResult.ok) throw new Error("[S3 stepModel] " + modelResult.error + " | DOM: " + snapshotDOM());
                await delay(300);

                // S4: Ratio
                await record("Selecting ratio 9:16 and resolution 2K");
                const ratioResult = await window.stepRatio();
                if (!ratioResult.ok) throw new Error("[S4 stepRatio] " + ratioResult.error + " | DOM: " + snapshotDOM());
                await delay(300);

                // S5: Upload assets
                await record("Uploading reference images");
                const uploadResult = await window.stepUpload(job);
                if (!uploadResult.ok) throw new Error("[S5 stepUpload] " + uploadResult.error + " | DOM: " + snapshotDOM());

                // S6: Prompt
                await record("Writing prompt");
                const promptResult = await window.stepPrompt(job);
                if (!promptResult.ok) throw new Error("[S6 stepPrompt] " + promptResult.error + " | DOM: " + snapshotDOM());

                // S7: Generate
                await record("Clicking generate button");
                const genResult = await window.stepGenerate();
                if (!genResult.ok) throw new Error("[S7 stepGenerate] " + genResult.error + " | DOM: " + snapshotDOM());
                await delay(1000);

                // S8: Wait for results
                await record("Waiting for generated images");
                const waitResult = await window.stepWait(job);
                if (!waitResult.ok) throw new Error("[S8 stepWait] " + waitResult.error + " | DOM: " + snapshotDOM());
                const resultImages = waitResult.data.images;
                await record("Found " + resultImages.length + " generated image(s)");

                // S9: Serialize
                const serializedImages = [];
                for (let i = 0; i < resultImages.length; i++) {
                  const img = resultImages[i];
                  try {
                    const resp = await fetch(img.src, { credentials: "include" });
                    if (!resp.ok) continue;
                    const blob = await resp.blob();
                    const mimeType = blob.type || "image/png";
                    const base64 = await blobToBase64(blob);
                    const ext = ({ "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif" })[mimeType] || ".png";
                    serializedImages.push({ filename: "result-" + String(i + 1).padStart(2, "0") + ext, mimeType, base64Data: base64, sourceUrl: img.src });
                  } catch (err) { await record("Failed to serialize image " + (i + 1) + ": " + err.message); }
                }

                await record("Saving results to local bridge", { imageCount: serializedImages.length });
                await postJson(su + "/v1/job/" + encodeURIComponent(job.id) + "/result", { images: serializedImages, logs });

                window.postMessage({ type: "manual:job:done" }, "*");
              } catch (error) {
                const reason = error instanceof Error ? error.message : String(error);
                console.error("[JimengImage ERROR]", reason, "\nFull logs:", logs);
                logs.push({ at: new Date().toISOString(), message: "Failed: " + reason });
                try { await postJson(su + "/v1/job/" + encodeURIComponent(job.id) + "/fail", { reason, logs }); } catch (_e) {}
                window.postMessage({ type: "manual:job:error", error: reason }, "*");
              }
            })();
          },
          args: [normalizedJob, serverUrl],
        });

        const result = await new Promise((resolve) => {
          const handleMessage = (event) => {
            if (event.data?.type === "manual:job:done") { window.removeEventListener("message", handleMessage); resolve("Job completed! Check page for results."); }
            if (event.data?.type === "manual:job:error") { window.removeEventListener("message", handleMessage); resolve("ERROR: " + event.data.error); }
            if (event.data?.type === "manual:job:log") { /* optionally show progress */ }
          };
          window.addEventListener("message", handleMessage);
          setTimeout(() => { window.removeEventListener("message", handleMessage); resolve("ERROR: Job timed out after 5 minutes"); }, 300000);
        });

        resultEl.textContent = result;
        resultEl.className = result.startsWith("ERROR") ? "manual-result error" : "manual-result";
      } catch (err) {
        resultEl.textContent = "ERROR: " + err.message;
        resultEl.className = "manual-result error";
        inputEl.classList.add("error");
      } finally {
        btn.disabled = false;
        btn.textContent = "Run Job Directly";
      }
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