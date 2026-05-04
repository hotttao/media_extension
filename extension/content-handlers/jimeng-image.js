/**
 * Jimeng (即梦) Image Generation Handler
 *
 * This handler implements the Jimeng image generation workflow by delegating
 * to shared step functions in jimeng-steps.js (loaded as a content script).
 */

// Shared step functions are on window (set by jimeng-steps.js content script).

// Re-export helpers from content-script via window (injected at runtime)
const controllerState = {}; // local fallback
const notifyProgress = () => { throw new Error("not injected"); };
const sendProgress = () => { throw new Error("not injected"); };
const delay = (ms) => new Promise(r => setTimeout(r, ms));
const bridgeFetch = (request) => chrome.runtime.sendMessage({ type: "bridge:fetch", request }).then(r => { if (!r.ok) throw new Error(r.error); return r; });
const postJson = async (url, payload) => {
  const resp = await bridgeFetch({ url, method: "POST", headers: { "Content-Type": "application/json" }, body: payload, responseType: "json" });
  return resp.json;
};
const blobToBase64 = (blob) => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onloadend = () => {
    const result = String(reader.result || "");
    const idx = result.indexOf(",");
    resolve(idx >= 0 ? result.slice(idx + 1) : result);
  };
  reader.onerror = reject;
  reader.readAsDataURL(blob);
});
const waitFor = (predicate, options = {}) => {
  const timeoutMs = options.timeoutMs ?? 120000;
  const intervalMs = options.intervalMs ?? 250;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = predicate();
    if (value) return value;
  }
  throw new Error(`Timed out waiting for ${options.label || "condition"}`);
};

export async function runJimengImageJob(job, serverUrl) {
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

    // Step 1: Navigate
    if (window.location.href !== job.targetUrl) {
      await record("Navigating to Jimeng");
      window.location.href = job.targetUrl;
      await waitFor(() => window.location.href.includes("type=image"), { timeoutMs: 30000, label: "jimeng image page" });
      await delay(2000);
    } else {
      await delay(1000);
    }

    // Wait for page to be fully interactive (combobox and file input present)
    await record("Waiting for page to be ready");
    try {
      waitFor(() => document.querySelector('[role="combobox"]'), { timeoutMs: 20000, label: "combobox" });
      waitFor(() => document.querySelector('input[type="file"]'), { timeoutMs: 10000, label: "file_input" });
    } catch (e) {
      throw new Error("Page not ready: " + e.message);
    }
    await delay(500);

    // Step 3: Select model 图片5.0 Lite
    await record("Selecting model 图片5.0 Lite");
    try {
      const modelResult = await window.stepModel();
      if (!modelResult.ok) {
        const dbg = snapshotDOM();
        throw new Error(`[S3 stepModel] ${modelResult.error} | DOM: ${dbg}`);
      }
    } catch (e) {
      if (e.message.includes("[S3")) throw e;
      throw new Error(`[S3 stepModel] ${e.message}`);
    }
    await delay(300);

    // Step 4: Select ratio 9:16 and resolution 2K
    await record("Selecting ratio 9:16 and resolution 2K");
    try {
      const ratioResult = await window.stepRatio();
      if (!ratioResult.ok) {
        const dbg = snapshotDOM();
        throw new Error(`[S4 stepRatio] ${ratioResult.error} | DOM: ${dbg}`);
      }
    } catch (e) {
      if (e.message.includes("[S4")) throw e;
      throw new Error(`[S4 stepRatio] ${e.message}`);
    }
    await delay(300);

    // Step 5: Upload reference images
    await record("Uploading reference images");
    try {
      const uploadResult = await window.stepUpload(job);
      if (!uploadResult.ok) {
        const dbg = snapshotDOM();
        throw new Error(`[S5 stepUpload] ${uploadResult.error} | DOM: ${dbg}`);
      }
    } catch (e) {
      if (e.message.includes("[S5")) throw e;
      throw new Error(`[S5 stepUpload] ${e.message}`);
    }

    // Step 6: Fill prompt
    await record("Writing prompt");
    try {
      const promptResult = await window.stepPrompt(job);
      if (!promptResult.ok) {
        const dbg = snapshotDOM();
        throw new Error(`[S6 stepPrompt] ${promptResult.error} | DOM: ${dbg}`);
      }
    } catch (e) {
      if (e.message.includes("[S6")) throw e;
      throw new Error(`[S6 stepPrompt] ${e.message}`);
    }

    // Step 7: Click generate button
    await record("Clicking generate button");
    try {
      const genResult = await window.stepGenerate();
      if (!genResult.ok) {
        const dbg = snapshotDOM();
        throw new Error(`[S7 stepGenerate] ${genResult.error} | DOM: ${dbg}`);
      }
    } catch (e) {
      if (e.message.includes("[S7")) throw e;
      throw new Error(`[S7 stepGenerate] ${e.message}`);
    }
    await delay(1000);

    // Step 8: Wait for results
    await record("Waiting for generated images");
    try {
      const waitResult = await window.stepWait(job);
      if (!waitResult.ok) {
        const dbg = snapshotDOM();
        throw new Error(`[S8 stepWait] ${waitResult.error} | DOM: ${dbg}`);
      }
      const resultImages = waitResult.data.images;
      await record(`Found ${resultImages.length} generated image(s)`);

      // Step 9: Serialize and report
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
      } catch (_postError) {
        // Ignore reporting errors.
      }
      controllerState.lastError = reason;
      controllerState.lastMessage = `Failed ${job.id}`;
      await chrome.runtime.sendMessage({ type: "content:failed", jobId: job.id, reason, state: { ...controllerState } });
    }
  }

  // Debug helper: snapshot key DOM state at the moment of failure
  function snapshotDOM() {
    try {
      const comboboxes = Array.from(document.querySelectorAll('[role="combobox"]'))
        .map(el => el.textContent.trim().slice(0, 60));
      const buttons = Array.from(document.querySelectorAll('button'))
        .filter(el => el.getBoundingClientRect().width > 0)
        .map(el => el.textContent.trim().slice(0, 40));
      const fileInputs = Array.from(document.querySelectorAll('input[type="file"]')).length;
      const url = window.location.href;
      return JSON.stringify({ comboboxes, buttons, fileInputs, url: url.slice(0, 80) });
    } catch {
      return "{}";
    }
  }
}


