/**
 * Jimeng (即梦) Video Generation Handler
 *
 * This handler implements the Jimeng video generation workflow:
 * 1. Navigate to targetUrl
 * 2. Click "视频生成" tab
 * 3. Select "Seedance1.0 首尾帧" model
 * 4. Upload first frame image
 * 5. Fill movement description and prompt
 * 6. Click generate button
 * 7. Poll for video result (8s stability check)
 * 8. Serialize and report results
 */

// Re-export helpers from content-script via window (injected at runtime)
const notifyProgress = () => { throw new Error("not injected"); };
const sendProgress = () => { throw new Error("not injected"); };
const delay = (ms) => new Promise(r => setTimeout(r, ms));
const isVisible = (el) => {
  if (!el) return false;
  const style = window.getComputedStyle(el);
  if (style.display === "none" || style.visibility === "hidden") return false;
  const rect = el.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
};
const waitFor = async (predicate, options = {}) => {
  const timeoutMs = options.timeoutMs ?? 120000;
  const intervalMs = options.intervalMs ?? 250;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = predicate();
    if (value) return value;
    await delay(intervalMs);
  }
  throw new Error(`Timed out waiting for ${options.label || "condition"}`);
};
const fetchAssetAsFile = async (asset) => {
  const response = await bridgeFetch({ url: asset.url, responseType: "blobBase64" });
  const binary = atob(response.base64Data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const mimeType = asset.mimeType || response.mimeType || "application/octet-stream";
  return new File([bytes], asset.name, { type: mimeType });
};
const postJson = async (url, payload) => {
  const resp = await bridgeFetch({ url, method: "POST", headers: { "Content-Type": "application/json" }, body: payload, responseType: "json" });
  return resp.json;
};
const bridgeFetch = (request) => chrome.runtime.sendMessage({ type: "bridge:fetch", request }).then(r => { if (!r.ok) throw new Error(r.error); return r; });
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

export async function runJimengVideoJob(job, serverUrl) {
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

    // Navigate to target URL if not already there
    if (window.location.href !== job.targetUrl) {
      await record("Navigating to Jimeng video page");
      window.location.href = job.targetUrl;
      await waitFor(() => window.location.href.includes("jimeng.jianying.com"), {
        timeoutMs: 30000,
        label: "page navigation",
      });
      await delay(2000);
    }

    // Step 2: Click "视频生成" tab (bottom of page)
    await record("Clicking 视频生成 tab");
    const videoTab = await waitFor(() => {
      return Array.from(document.querySelectorAll("div, span, button")).find(
        (el) => isVisible(el) && el.innerText && el.innerText.includes("视频生成")
      );
    }, { timeoutMs: 30000, label: "视频生成 tab" });

    if (videoTab) {
      videoTab.click();
      await delay(1000);
    }

    // Step 3: Select "Seedance1.0 首尾帧" model
    await record("Selecting Seedance1.0 首尾帧 model");
    const modelOption = await waitFor(() => {
      return Array.from(document.querySelectorAll("div, span, button")).find(
        (el) => isVisible(el) && el.innerText && el.innerText.includes("Seedance1.0 首尾帧")
      );
    }, { timeoutMs: 30000, label: "Seedance1.0 model option" });

    if (modelOption) {
      modelOption.click();
      await delay(1000);
    }

    // Step 4: Upload first frame image
    await record("Uploading first frame image");
    const firstFrameAsset = job.assets?.find((a) => a.label === "firstFrame");
    if (firstFrameAsset) {
      await uploadFirstFrameImage(firstFrameAsset);
    } else if (job.assets?.length > 0) {
      await uploadFirstFrameImage(job.assets[0]);
    }

    // Step 5: Fill movement description
    await record("Filling movement description");
    const movementText = job.movement || job.movementId || job.prompt || "";
    const movementInput = await waitFor(() => {
      // Look for textarea or input that could be movement description
      return Array.from(document.querySelectorAll("textarea, input")).find(
        (el) => isVisible(el) && (el.placeholder?.includes("运动") || el.placeholder?.includes("movement"))
      );
    }, { timeoutMs: 30000, label: "movement input" });

    if (movementInput) {
      fillInput(movementInput, movementText);
      await delay(500);
    }

    // Step 6: Fill prompt text
    await record("Filling prompt text");
    const promptInput = await waitFor(() => {
      // Look for main prompt textarea
      return Array.from(document.querySelectorAll("textarea")).find(
        (el) => isVisible(el) && (el.placeholder?.includes("描述") || el.placeholder?.includes("prompt"))
      );
    }, { timeoutMs: 30000, label: "prompt input" });

    if (promptInput) {
      fillInput(promptInput, job.prompt || "");
      await delay(500);
    }

    // Step 7: Click generate button
    await record("Clicking generate button");
    const generateButton = await waitFor(() => {
      return Array.from(document.querySelectorAll("button")).find(
        (el) => isVisible(el) && !el.disabled && (
          el.innerText?.includes("生成") || el.innerText?.includes("生成视频")
        )
      );
    }, { timeoutMs: 30000, label: "generate button" });

    if (generateButton) {
      generateButton.click();
    } else {
      throw new Error("Generate button not found");
    }

    // Step 8: Poll for video result (8s stability check)
    await record("Waiting for video result");
    const videoResult = await waitForVideoResult(job.timeoutSeconds ? job.timeoutSeconds * 1000 : 600000);

    await record(`Found video result`, {
      sourceType: videoResult.sourceType,
      url: videoResult.url,
    });

    // Step 9: Serialize video and report
    await record("Serializing video");
    const serializedVideo = await serializeVideo(videoResult);

    await record("Saving results to local bridge", {
      videoFilename: serializedVideo.filename,
    });

    await postJson(`${serverUrl}/v1/job/${encodeURIComponent(job.id)}/result`, {
      videos: [serializedVideo],
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

async function uploadFirstFrameImage(asset) {
  // Find file input for image upload
  const fileInput = await waitFor(() => {
    return Array.from(document.querySelectorAll("input[type='file']")).find(
      (input) => isVisible(input) || input.offsetParent !== null
    );
  }, { timeoutMs: 30000, label: "file input for image upload" });

  if (!fileInput) {
    throw new Error("File input not found for image upload");
  }

  const file = await fetchAssetAsFile(asset);
  const dataTransfer = new DataTransfer();
  dataTransfer.items.add(file);
  fileInput.files = dataTransfer.files;
  fileInput.dispatchEvent(new Event("change", { bubbles: true }));
  fileInput.dispatchEvent(new Event("input", { bubbles: true }));

  await delay(2000);
}

function fillInput(input, text) {
  input.focus();
  const currentValue = input.value || "";
  if (currentValue === text) {
    return;
  }

  // Clear existing content
  if ("value" in input) {
    input.value = "";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  // Use execCommand for contenteditable or direct value for inputs
  if ("value" in input) {
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
}

async function waitForVideoResult(timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let stableSince = 0;
  let lastVideoSrc = "";

  while (Date.now() < deadline) {
    // Check for video element
    const videoElement = document.querySelector("video");
    if (videoElement && isVisible(videoElement) && videoElement.src && videoElement.src !== lastVideoSrc) {
      lastVideoSrc = videoElement.src;

      // Check stability - 8 seconds
      if (!stableSince) {
        stableSince = Date.now();
      }
      if (Date.now() - stableSince > 8000) {
        return {
          sourceType: "videoElement",
          url: videoElement.src,
          element: videoElement,
        };
      }
    }

    // Check for download link
    const downloadLink = Array.from(document.querySelectorAll("a[href]")).find(
      (a) => a.href && (a.href.includes(".mp4") || a.href.includes(".webm"))
    );
    if (downloadLink && downloadLink.href !== lastVideoSrc) {
      lastVideoSrc = downloadLink.href;

      // Verify it's stable
      if (!stableSince) {
        stableSince = Date.now();
      }
      if (Date.now() - stableSince > 8000) {
        return {
          sourceType: "downloadLink",
          url: downloadLink.href,
          element: downloadLink,
        };
      }
    }

    await delay(2000);
  }

  throw new Error("Timed out while waiting for video result");
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

async function serializeVideo(videoResult) {
  let blob;
  let mimeType = "video/mp4";

  if (videoResult.sourceType === "videoElement") {
    const videoSrc = videoResult.url;
    const response = await fetch(videoSrc, { credentials: "include" });
    if (!response.ok) {
      throw new Error(`Failed to fetch video: ${response.status}`);
    }
    blob = await response.blob();
    mimeType = blob.type || "video/mp4";
  } else if (videoResult.sourceType === "downloadLink") {
    const linkHref = videoResult.url;
    const response = await fetch(linkHref, { credentials: "include" });
    if (!response.ok) {
      throw new Error(`Failed to fetch video from download link: ${response.status}`);
    }
    blob = await response.blob();
    mimeType = blob.type || "video/mp4";
  } else {
    throw new Error(`Unknown video source type: ${videoResult.sourceType}`);
  }

  const extension = mimeType.includes("webm") ? ".webm" : ".mp4";
  const base64Data = await blobToBase64(blob);

  return {
    filename: `result-001${extension}`,
    mimeType,
    base64Data,
    sourceUrl: videoResult.url,
  };
}
