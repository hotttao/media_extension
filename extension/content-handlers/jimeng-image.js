/**
 * Jimeng (即梦) Image Generation Handler
 *
 * This handler implements the Jimeng image generation workflow:
 * 1. Navigate to target URL
 * 2. Click "图片生成" tab
 * 3. Select "图片5.0 Lite 9:16 2K" model
 * 4. Upload 3 reference images (人物, 服装, 场景)
 * 5. Fill prompt text
 * 6. Click generate button
 * 7. Wait for stable results (8s stability check)
 * 8. Collect up to 4 result images
 * 9. Serialize and report results
 */

// Re-export helpers from content-script via window (injected at runtime)
const controllerState = {}; // local fallback
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
const extensionFromMimeType = (mimeType) => ({ "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif" }[mimeType] || ".png");

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

    // Step 1: Navigate to target URL
    if (window.location.href !== job.targetUrl) {
      await record("Navigating to Jimeng");
      window.location.href = job.targetUrl;
      await waitFor(() => window.location.href.includes("jimeng"), {
        timeoutMs: 30000,
        label: "Jimeng page load",
      });
      await delay(2000);
    }

    // Step 2: Click "图片生成" tab
    await record("Clicking 图片生成 tab");
    const imageTabCandidates = () => {
      const allText = document.querySelectorAll("*");
      const results = [];
      for (const el of allText) {
        if (el.childNodes.length === 1 && el.textContent?.trim() === "图片生成") {
          results.push(el);
        }
      }
      return results;
    };

    let imageTab = null;
    const tabs = imageTabCandidates();
    for (const tab of tabs) {
      if (isVisible(tab)) {
        imageTab = tab;
        break;
      }
    }

    if (!imageTab) {
      // Try clicking by text content using evaluate
      const clicked = await document.evaluate(() => {
        const elements = document.querySelectorAll("*");
        for (const el of elements) {
          if (el.childNodes.length === 1 && el.textContent?.trim() === "图片生成") {
            el.click();
            return true;
          }
        }
        return false;
      });
      if (!clicked) {
        throw new Error("图片生成 tab not found");
      }
    } else {
      imageTab.click();
    }
    await delay(1000);

    // Step 3: Select "图片5.0 Lite" model and "9:16 2K" ratio/resolution
    await record("Selecting model 图片5.0 Lite and ratio 9:16 resolution 2K");

    // Click model combobox to open dropdown
    const allText = document.querySelectorAll("*");
    let modelCombobox = null;
    for (const el of allText) {
      const role = el.getAttribute("role");
      const text = el.textContent?.trim() || "";
      if (role === "combobox" && (text.includes("4.6") || text.includes("5.0"))) {
        modelCombobox = el;
        break;
      }
    }
    if (!modelCombobox) throw new Error("Model combobox not found");
    modelCombobox.click();
    await delay(500);

    // Wait for listbox dropdown
    const listbox = await waitFor(() => document.querySelector('[role="listbox"]'), { timeoutMs: 5000, label: "model listbox" });
    if (!listbox) throw new Error("Model listbox not visible");
    await delay(300);

    // Click 图片5.0 Lite option
    const allEls = document.querySelectorAll("*");
    let liteOption = null;
    for (const el of allEls) {
      if (el.getAttribute("role") === "option" && el.textContent?.trim().includes("5.0") && el.textContent?.trim().includes("Lite")) {
        liteOption = el;
        break;
      }
    }
    if (!liteOption) throw new Error("图片5.0 Lite option not found");
    liteOption.click();
    await delay(500);

    // Close dropdown with Escape key
    await page.keyboard.press("Escape");
    await delay(300);

    // Click ratio/resolution button (shows "智能比例 高清 2K") to open popover
    let ratioTarget = null;
    for (const el of allEls) {
      if (el.tagName === "BUTTON" && el.textContent?.trim().includes("智能比例")) {
        ratioTarget = el;
        break;
      }
    }
    if (!ratioTarget) throw new Error("Ratio button not found");
    ratioTarget.click();
    await delay(500);

    // Click ratio 9:16 and resolution 2k (radios are in DOM, hidden)
    const allRadios = Array.from(document.querySelectorAll('input[type="radio"]'));
    let ratioSelected = false;
    let resSelected = false;
    for (const radio of allRadios) {
      if (radio.value === "9:16") {
        radio.click();
        ratioSelected = true;
      }
      if (radio.value === "2k") {
        radio.click();
        resSelected = true;
      }
    }
    if (!ratioSelected) throw new Error("Ratio 9:16 not found");
    if (!resSelected) throw new Error("Resolution 2k not found");

    await delay(300);
    await record("Model and ratio/resolution selected");

    // Step 4: Upload 3 reference images
    await record("Uploading reference images");

    // Find upload slots - look for upload-related elements
    const uploadSlotCandidates = () => {
      // Look for elements that could be upload slots
      // Typically these are divs or areas with upload-related attributes
      const slots = [];
      const uploadAreas = document.querySelectorAll("[data-testid*='upload'], [class*='upload'], [class*='Upload']");
      for (const area of uploadAreas) {
        if (isVisible(area)) {
          slots.push(area);
        }
      }
      return slots;
    };

    // Also look for input[type="file"] elements
    const fileInputs = () => {
      return Array.from(document.querySelectorAll("input[type='file']")).filter(isVisible);
    };

    // Try to find upload slots or file inputs
    let uploadSlots = uploadSlotCandidates();
    let fileInputElements = fileInputs();

    if (uploadSlots.length === 0 && fileInputElements.length === 0) {
      // Look for clickable upload areas
      const clickableUploads = () => {
        const allEls = document.querySelectorAll("*");
        const results = [];
        for (const el of allEls) {
          const text = el.textContent?.trim() || "";
          if ((text.includes("上传") || text.includes("添加图片") || el.getAttribute("aria-label")?.includes("upload")) && isVisible(el)) {
            results.push(el);
          }
        }
        return results;
      };
      uploadSlots = clickableUploads();
    }

    // Upload each asset to its corresponding slot
    const labelToIndex = { "人物": 0, "服装": 1, "场景": 2 };

    for (const asset of job.assets || []) {
      const slotIndex = labelToIndex[asset.label] ?? job.assets.indexOf(asset);
      await record(`Uploading asset: ${asset.label}`, { url: asset.url, slotIndex });

      // Try to find the upload slot
      let uploaded = false;

      // Method 1: Try file inputs
      const inputs = fileInputs();
      if (inputs.length > slotIndex) {
        const input = inputs[slotIndex];
        const file = await fetchAssetAsFile(asset);
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));
        uploaded = true;
        await delay(500);
      }

      // Method 2: Try upload slots
      if (!uploaded && uploadSlots.length > slotIndex) {
        const slot = uploadSlots[slotIndex];
        // Click to open file dialog
        slot.click();
        await delay(500);

        // Find file input that appears
        const newInput = await waitFor(() => {
          const inputs = fileInputs();
          return inputs.length > 0 ? inputs[inputs.length - 1] : null;
        }, { timeoutMs: 5000, label: "file input after click" });

        if (newInput) {
          const file = await fetchAssetAsFile(asset);
          const transfer = new DataTransfer();
          transfer.items.add(file);
          newInput.files = transfer.files;
          newInput.dispatchEvent(new Event("change", { bubbles: true }));
          uploaded = true;
          await delay(500);
        }
      }

      // Method 3: Try clicking text-based upload buttons
      if (!uploaded) {
        const clicked = await document.evaluate((label) => {
          const elements = document.querySelectorAll("*");
          for (const el of elements) {
            const text = el.textContent?.trim() || "";
            if (text === label || text.includes(label)) {
              if (isVisible(el)) {
                el.click();
                return true;
              }
            }
          }
          return false;
        }, asset.label);

        if (clicked) {
          await delay(500);
          const newInput = await waitFor(() => {
            const inputs = fileInputs();
            return inputs.length > 0 ? inputs[inputs.length - 1] : null;
          }, { timeoutMs: 5000, label: "file input after label click" });

          if (newInput) {
            const file = await fetchAssetAsFile(asset);
            const transfer = new DataTransfer();
            transfer.items.add(file);
            newInput.files = transfer.files;
            newInput.dispatchEvent(new Event("change", { bubbles: true }));
            uploaded = true;
            await delay(500);
          }
        }
      }

      if (!uploaded) {
        throw new Error(`Failed to upload asset: ${asset.label}`);
      }

      // Wait for image preview to appear
      await waitFor(() => {
        const previews = document.querySelectorAll("img[src*='data:'],[src*='blob:']");
        return previews.length > slotIndex;
      }, { timeoutMs: 10000, label: `image preview for ${asset.label}` });
    }

    // Step 5: Fill prompt text
    await record("Writing prompt");
    const promptCandidates = () => {
      const selectors = [
        "textarea",
        "input[type='text']",
        "input[placeholder*='描述']",
        "div[contenteditable='true']",
      ];
      const results = [];
      for (const sel of selectors) {
        const els = document.querySelectorAll(sel);
        for (const el of els) {
          if (isVisible(el)) {
            results.push(el);
          }
        }
      }
      return results;
    };

    let promptEl = null;
    const promptEls = promptCandidates();
    for (const el of promptEls) {
      // Find the main prompt input (usually a textarea or the largest input)
      if (el.tagName === "TEXTAREA" || el.getAttribute("placeholder")?.includes("描述")) {
        promptEl = el;
        break;
      }
      if (!promptEl) {
        promptEl = el;
      }
    }

    if (promptEl) {
      if ("value" in promptEl) {
        promptEl.focus();
        promptEl.value = "";
        promptEl.value = job.prompt;
        promptEl.dispatchEvent(new InputEvent("input", { bubbles: true, data: job.prompt }));
        promptEl.dispatchEvent(new Event("change", { bubbles: true }));
      } else {
        promptEl.focus();
        promptEl.textContent = "";
        promptEl.textContent = job.prompt;
        promptEl.dispatchEvent(new InputEvent("input", { bubbles: true, data: job.prompt }));
      }
      await delay(300);
    } else {
      throw new Error("Prompt input not found");
    }

    // Step 6: Click generate button
    await record("Clicking generate button");
    const generateCandidates = () => {
      const allEls = document.querySelectorAll("*");
      const results = [];
      for (const el of allEls) {
        const text = el.textContent?.trim() || "";
        if (text.includes("生成")) {
          results.push(el);
        }
      }
      return results;
    };

    let generateBtn = null;
    const btns = generateCandidates();
    for (const btn of btns) {
      if (isVisible(btn) && !btn.disabled) {
        generateBtn = btn;
        break;
      }
    }

    if (!generateBtn) {
      throw new Error("Generate button not found");
    }

    generateBtn.click();
    await delay(1000);

    // Step 7: Wait for results with 8s stability check
    await record("Waiting for generated images");

    // Collect baseline image keys
    const baselineImageKeys = new Set();
    const baselineImgs = document.querySelectorAll("img");
    for (const img of baselineImgs) {
      if (img.src) {
        baselineImageKeys.add(img.src);
      }
    }

    // Wait for stable results (8s stability check)
    const deadline = Date.now() + (job.timeoutSeconds ? job.timeoutSeconds * 1000 : 600000);
    let stableSince = 0;
    let lastKeys = [];
    let resultImages = [];

    while (Date.now() < deadline) {
      // Find result images
      const currentImgs = Array.from(document.querySelectorAll("img")).filter((img) => {
        if (!isVisible(img)) return false;
        if (baselineImageKeys.has(img.src)) return false;
        const rect = img.getBoundingClientRect();
        return rect.width > 100 && rect.height > 100;
      });

      if (currentImgs.length > 0) {
        const currentKeys = currentImgs.map((img) => img.src).sort();

        const sameAsPrevious =
          currentKeys.length === lastKeys.length && currentKeys.every((key, idx) => key === lastKeys[idx]);

        if (sameAsPrevious) {
          if (!stableSince) {
            stableSince = Date.now();
          }
          if (Date.now() - stableSince > 8000) {
            resultImages = currentImgs;
            break;
          }
        } else {
          stableSince = Date.now();
          lastKeys = currentKeys;
        }
      }

      await delay(2000);
    }

    if (resultImages.length === 0) {
      throw new Error("Timed out while waiting for generated images");
    }

    await record(`Found ${resultImages.length} generated image(s)`);

    // Step 8: Collect up to 4 result images
    const maxResults = 4;
    const selectedImages = resultImages.slice(0, maxResults);

    // Step 9: Serialize and report results
    const serializedImages = [];
    for (let i = 0; i < selectedImages.length; i++) {
      const img = selectedImages[i];
      try {
        const response = await fetch(img.src, { credentials: "include" });
        if (!response.ok) {
          continue;
        }
        const blob = await response.blob();
        const mimeType = blob.type || "image/png";
        const base64 = await blobToBase64(blob);
        serializedImages.push({
          filename: `result-${String(i + 1).padStart(2, "0")}${extensionFromMimeType(mimeType)}`,
          mimeType,
          base64Data: base64,
          sourceUrl: img.src,
        });
      } catch (err) {
        await record(`Failed to serialize image ${i + 1}: ${err.message}`);
      }
    }

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

// Helper functions used by the handler
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
