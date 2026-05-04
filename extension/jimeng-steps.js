/**
 * Jimeng Steps — shared step functions for jimeng image automation.
 *
 * Each step function returns { ok, data, error }.
 * Functions are assigned to window so both content-script.js and
 * jimeng-image.js (via dynamic import) can access them.
 */

(function() {
  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  const charCodesOf = (str) => Array.from(str).map(c => c.charCodeAt(0));

  const sameChars = (a, b) => {
    const ca = charCodesOf(a), cb = charCodesOf(b);
    if (ca.length !== cb.length) return false;
    return ca.every((c, i) => c === cb[i]);
  };

  const textLike = (domText, target) => {
    if (!domText) return false;
    const dt = domText.trim();
    if (dt === target) return true;
    return sameChars(dt, target);
  };

  const textIncludes = (domText, target) => {
    if (!domText) return false;
    const dt = domText.trim();
    if (dt.includes(target)) return true;
    const dc = charCodesOf(dt), tc = charCodesOf(target);
    if (tc.length > dc.length) return false;
    outer: for (let i = 0; i <= dc.length - tc.length; i++) {
      for (let j = 0; j < tc.length; j++) { if (dc[i+j] !== tc[j]) continue outer; }
      return true;
    }
    return false;
  };

  const isVisible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };

  const delay = (ms) => new Promise(r => setTimeout(r, ms));

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

  const bridgeFetch = (request) => chrome.runtime.sendMessage({ type: "bridge:fetch", request })
    .then(r => { if (!r.ok) throw new Error(r.error); return r; });

  // ---------------------------------------------------------------------------
  // Step 1: Navigate
  // ---------------------------------------------------------------------------
  async function stepNav(targetUrl) {
    if (window.location.href !== targetUrl) {
      window.location.href = targetUrl;
      return { ok: false, data: { status: "navigating" }, error: null };
    }
    return { ok: true, data: { status: "already_on_page", url: window.location.href }, error: null };
  }

  // ---------------------------------------------------------------------------
  // Step 2: Click "图片生成" tab (skip if already on type=image page)
  // ---------------------------------------------------------------------------
  async function stepTab() {
    // If already on type=image, just wait for the combobox to confirm page is ready
    if (window.location.href.includes("type=image")) {
      try {
        waitFor(() => document.querySelector('[role="combobox"]'), { timeoutMs: 15000, label: "combobox" });
        return { ok: true, data: { status: "already_on_image_tab" }, error: null };
      } catch {
        return { ok: false, data: null, error: "type=image page loaded but combobox not found" };
      }
    }

    const candidates = () => Array.from(document.querySelectorAll("*")).filter(el =>
      el.childNodes.length === 1 && (textLike(el.textContent, "图片生成") || textLike(el.textContent, "视频生成"))
    );

    let tab = null;
    const tabs = candidates();
    for (const t of tabs) {
      if (isVisible(t)) { tab = t; break; }
    }

    if (!tab) {
      const clicked = await document.evaluate(() => {
        const els = document.querySelectorAll("*");
        for (const el of els) {
          if (el.childNodes.length === 1 && textLike(el.textContent, "图片生成")) {
            el.click(); return true;
          }
        }
        return false;
      });
      if (!clicked) return { ok: false, data: null, error: "图片生成 tab not found" };
      await delay(1000);
      // Wait for page to transition
      waitFor(() => window.location.href.includes("type=image"), { timeoutMs: 15000, label: "type=image URL" });
      waitFor(() => document.querySelector('[role="combobox"]'), { timeoutMs: 15000, label: "combobox" });
      return { ok: true, data: { status: "clicked_via_evaluate" }, error: null };
    }

    const parentClickable = tab.parentElement;
    const isMenuItem = parentClickable && (parentClickable.getAttribute("role")?.includes("menu") ||
      parentClickable.className?.includes("menu") || parentClickable.tagName === "LI");

    if (!isMenuItem && textLike(tab.textContent, "图片生成")) {
      const parentVisible = parentClickable && isVisible(parentClickable);
      if (parentVisible) {
        parentClickable.click();
        await delay(1000);
        const secondClick = Array.from(document.querySelectorAll("*")).find(el =>
          textLike(el.textContent, "图片生成") && isVisible(el) && el !== tab
        );
        if (secondClick) { secondClick.click(); }
        // Wait for page transition
        waitFor(() => window.location.href.includes("type=image"), { timeoutMs: 15000, label: "type=image URL" });
        return { ok: true, data: { status: "parent_then_option", parentTag: parentClickable.tagName }, error: null };
      }
      tab.click();
      await delay(1000);
      const option = Array.from(document.querySelectorAll("*")).find(el =>
        textLike(el.textContent, "图片生成") && isVisible(el) && el !== tab
      );
      if (option) { option.click(); }
      waitFor(() => window.location.href.includes("type=image"), { timeoutMs: 15000, label: "type=image URL" });
      return { ok: true, data: { status: "trigger_then_option" }, error: null };
    }

    tab.click();
    waitFor(() => window.location.href.includes("type=image"), { timeoutMs: 15000, label: "type=image URL" });
    return { ok: true, data: { status: "menu_item_clicked" }, error: null };
  }

  // ---------------------------------------------------------------------------
  // Step 3: Select model (图片5.0 Lite)
  // ---------------------------------------------------------------------------
  async function stepModel() {
    const delayMs = 500;
    const allEls = () => Array.from(document.querySelectorAll("*"));

    // Wait for combobox to appear (page may still be rendering)
    try {
      waitFor(() => document.querySelector('[role="combobox"]'), { timeoutMs: 20000, label: "model_combobox" });
    } catch {
      const comboboxes = allEls().filter(el => el.getAttribute("role") === "combobox");
      const comboboxTexts = comboboxes.map(el => el.textContent?.trim().slice(0, 30)).join(" | ");
      return { ok: false, data: { comboboxTexts }, error: "Model combobox not found (timed out waiting)" };
    }

    const comboboxes = allEls().filter(el => el.getAttribute("role") === "combobox");
    const comboboxTexts = comboboxes.map(el => el.textContent?.trim().slice(0, 30)).join(" | ");
    const modelCombobox = comboboxes.find(el =>
      el.textContent?.trim().includes("5.0") || el.textContent?.trim().includes("4.6")
    );
    if (!modelCombobox) return { ok: false, data: { comboboxTexts }, error: "Model combobox not found" };

    modelCombobox.click();
    await delay(delayMs);
    console.log("[stepModel] clicked model combobox");

    const listbox = document.querySelector('[role="listbox"]');
    if (!listbox) return { ok: false, data: null, error: "Model listbox not visible" };
    await delay(delayMs);

    const options = Array.from(document.querySelectorAll('[role="option"]')).filter(isVisible);
    console.log("[stepModel] options found:", options.length, options.map(o => o.textContent?.trim().slice(0, 30)));
    const liteOption = options.find(el =>
      el.textContent?.trim().includes("5.0") && el.textContent?.trim().includes("Lite")
    );
    if (!liteOption) {
      const optionTexts = options.map(o => o.textContent?.trim().slice(0, 40)).join(" | ");
      return { ok: false, data: { optionTexts }, error: "图片5.0 Lite not found" };
    }

    liteOption.click();
    await delay(delayMs);
    document.body.click();
    await delay(300);

    const modelText = modelCombobox?.textContent?.trim() || "";
    const modelChanged = modelText.includes("5.0") || modelText.includes("Lite");
    if (!modelChanged) return { ok: false, data: { modelText }, error: "Model combobox text unchanged" };
    return { ok: true, data: { modelText }, error: null };
  }

  // ---------------------------------------------------------------------------
  // Step 4: Select ratio (9:16) and resolution (2K)
  // ---------------------------------------------------------------------------
  async function stepRatio() {
    const delayMs = 500;
    const allButtons = () => Array.from(document.querySelectorAll("button")).filter(isVisible);

    // Find the ratio/resolution button (e.g. "9:16 高清 2K" or similar)
    const ratioBtn = allButtons().find(el => {
      const text = el.textContent?.trim() || "";
      const hasResolution = text.includes("K");
      const hasRatioDigit = /\d+:\d+/.test(text);
      const hasIntelligent = text.includes("\u667A\u80FD\u6BD4\u4F8B");
      return hasResolution && (hasRatioDigit || hasIntelligent);
    });
    if (!ratioBtn) return { ok: false, data: null, error: "Ratio button not found" };

    ratioBtn.click();
    await delay(delayMs);
    console.log("[stepRatio] clicked ratio button, now looking for options");

    // After clicking, look for dropdown with ratio and resolution options
    // The dropdown may contain buttons, not radio inputs
    // Look for buttons containing "9:16" text for ratio
    const dropdownButtons = () => Array.from(document.querySelectorAll("button")).filter(isVisible);

    // Try to find ratio option button
    const ratioOption = dropdownButtons().find(el =>
      el.textContent?.trim().includes("9:16") ||
      (/\d+:\d+/.test(el.textContent?.trim() || ""))
    );
    // Try to find resolution option button
    const resOption = dropdownButtons().find(el => {
      const text = el.textContent?.trim() || "";
      return text.includes("2K") || text.includes("2k") || text.includes("高清");
    });

    console.log("[stepRatio] ratioOption:", ratioOption?.textContent?.trim().slice(0, 40), "resOption:", resOption?.textContent?.trim().slice(0, 40));

    let ratioChanged = false, resChanged = false;
    if (ratioOption) { ratioOption.click(); ratioChanged = true; await delay(200); }
    if (resOption) { resOption.click(); resChanged = true; await delay(200); }

    // Fallback: also check for radio inputs in case the page does use them
    if (!ratioChanged) {
      const allRadios = Array.from(document.querySelectorAll('input[type="radio"]'));
      console.log("[stepRatio] no button match, checking radios:", allRadios.map(r => ({ value: r.value, checked: r.checked })));
      const ratioRadio = allRadios.find(r => r.value === "9:16");
      const resRadio = allRadios.find(r => r.value === "2k");
      if (ratioRadio) { ratioRadio.click(); ratioChanged = ratioRadio.checked; await delay(200); }
      if (resRadio) { resRadio.click(); resChanged = resRadio.checked; await delay(200); }
    }

    document.body.click();
    await delay(300);

    if (!ratioChanged) return { ok: false, data: null, error: "Ratio 9:16 not selected" };
    return { ok: true, data: { ratio: "9:16", resolution: resChanged ? "2K" : null }, error: null };
  }

  // ---------------------------------------------------------------------------
  // Step 5: Upload reference images
  // ---------------------------------------------------------------------------
  async function stepUpload(job) {
    const labelToIndex = { "人物": 0, "服装": 1, "场景": 2 };

    const fetchAssetAsFile = async (asset) => {
      const response = await bridgeFetch({ url: asset.url, responseType: "blobBase64" });
      const binary = atob(response.base64Data);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const mimeType = asset.mimeType || response.mimeType || "application/octet-stream";
      return new File([bytes], asset.name, { type: mimeType });
    };

    const fileInputs = () => Array.from(document.querySelectorAll("input[type='file']"));

    const uploadSlots = () => {
      const areas = document.querySelectorAll("[data-testid*='upload'], [class*='upload'], [class*='Upload']");
      return Array.from(areas).filter(isVisible);
    };

    const clickableUploads = () => {
      const results = [];
      for (const el of document.querySelectorAll("*")) {
        const text = el.textContent?.trim() || "";
        if ((textIncludes(text, "上传") || textIncludes(text, "添加图片") || el.getAttribute("aria-label")?.includes("upload")) && isVisible(el)) {
          results.push(el);
        }
      }
      return results;
    };

    for (const asset of job.assets || []) {
      const slotIndex = labelToIndex[asset.label] ?? job.assets.indexOf(asset);

      // Method 1: Direct file input
      const inputs = fileInputs();
      if (inputs.length > slotIndex) {
        const input = inputs[slotIndex];
        const file = await fetchAssetAsFile(asset);
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));
        await delay(500);
        await waitFor(() => {
          const previews = document.querySelectorAll("img[src*='data:'],[src*='blob:']");
          return previews.length > slotIndex;
        }, { timeoutMs: 10000, label: `image preview ${asset.label}` });
        continue;
      }

      // Method 2: Upload slot click
      let slots = uploadSlots();
      if (slots.length > slotIndex) {
        slots[slotIndex].click();
        await delay(500);
        const newInput = await waitFor(() => {
          const ins = fileInputs();
          return ins.length > 0 ? ins[ins.length - 1] : null;
        }, { timeoutMs: 5000, label: "file input after slot click" });
        if (newInput) {
          const file = await fetchAssetAsFile(asset);
          const transfer = new DataTransfer();
          transfer.items.add(file);
          newInput.files = transfer.files;
          newInput.dispatchEvent(new Event("change", { bubbles: true }));
          await delay(500);
          await waitFor(() => {
            const previews = document.querySelectorAll("img[src*='data:'],[src*='blob:']");
            return previews.length > slotIndex;
          }, { timeoutMs: 10000, label: `image preview ${asset.label}` });
          continue;
        }
      }

      // Method 3: Text-based upload buttons
      const clicked = await document.evaluate((label) => {
        const els = document.querySelectorAll("*");
        for (const el of els) {
          const text = el.textContent?.trim() || "";
          if (text === label || text.includes(label)) {
            if (isVisible(el)) { el.click(); return true; }
          }
        }
        return false;
      }, asset.label);

      if (clicked) {
        await delay(500);
        const newInput = await waitFor(() => {
          const ins = fileInputs();
          return ins.length > 0 ? ins[ins.length - 1] : null;
        }, { timeoutMs: 5000, label: "file input after label click" });
        if (newInput) {
          const file = await fetchAssetAsFile(asset);
          const transfer = new DataTransfer();
          transfer.items.add(file);
          newInput.files = transfer.files;
          newInput.dispatchEvent(new Event("change", { bubbles: true }));
          await delay(500);
          await waitFor(() => {
            const previews = document.querySelectorAll("img[src*='data:'],[src*='blob:']");
            return previews.length > slotIndex;
          }, { timeoutMs: 10000, label: `image preview ${asset.label}` });
          continue;
        }
      }

      return { ok: false, data: { label: asset.label }, error: `Failed to upload: ${asset.label}` };
    }

    return { ok: true, data: { count: job.assets?.length ?? 0 }, error: null };
  }

  // ---------------------------------------------------------------------------
  // Step 6: Fill prompt text
  // ---------------------------------------------------------------------------
  async function stepPrompt(job) {
    const promptCandidates = () => {
      const selectors = ["textarea", "input[type='text']", "input[placeholder*='描述']", "div[contenteditable='true']", "div.tiptap", ".tiptap"];
      const results = [];
      for (const sel of selectors) {
        for (const el of document.querySelectorAll(sel)) {
          if (el.getAttribute("contenteditable") === "true" || isVisible(el)) {
            results.push(el);
          }
        }
      }
      return results;
    };

    let promptEl = null;
    const promptEls = promptCandidates();
    for (const el of promptEls) {
      if (el.tagName === "TEXTAREA" || textIncludes(el.getAttribute("placeholder"), "描述")) {
        promptEl = el; break;
      }
    }
    if (!promptEl) {
      for (const el of promptEls) {
        if (el.getAttribute("contenteditable") === "true" || el.classList.contains("tiptap")) {
          promptEl = el; break;
        }
      }
    }
    if (!promptEl && promptEls.length > 0) promptEl = promptEls[0];

    if (!promptEl) return { ok: false, data: null, error: "Prompt input not found" };

    console.log("[stepPrompt] using prompt element:", promptEl.tagName, promptEl.className?.slice(0, 30), "placeholder:", promptEl.getAttribute("placeholder"), "contenteditable:", promptEl.getAttribute("contenteditable"));

    if ("value" in promptEl) {
      promptEl.focus();
      promptEl.value = "";
      promptEl.value = job.prompt || "";
      promptEl.dispatchEvent(new InputEvent("input", { bubbles: true, data: job.prompt }));
      promptEl.dispatchEvent(new Event("change", { bubbles: true }));
    } else {
      promptEl.focus();
      promptEl.textContent = "";
      promptEl.textContent = job.prompt || "";
      promptEl.dispatchEvent(new InputEvent("input", { bubbles: true, data: job.prompt }));
    }
    await delay(300);
    return { ok: true, data: { promptLength: (job.prompt || "").length }, error: null };
  }

  // ---------------------------------------------------------------------------
  // Step 7: Click generate button
  // ---------------------------------------------------------------------------
  async function stepGenerate() {
    const allBtns = () => Array.from(document.querySelectorAll("button")).filter(isVisible);

    // Filter buttons containing "生成" and not disabled
    const btns = allBtns().filter(el =>
      textIncludes(el.textContent, "生成") && !el.disabled
    );

    if (btns.length === 0) return { ok: false, data: null, error: "Generate button not found" };

    // Prefer the button whose text is exactly "生成" or starts with "生成"
    // and has a distinct appearance (larger, prominent placement)
    const exactGenerate = btns.find(el => {
      const text = el.textContent?.trim() || "";
      return text === "生成" || text.startsWith("生成") && text.length < 10;
    });

    // Fall back to first button with "生成" if no exact match
    const targetBtn = exactGenerate || btns[0];

    // Debug: log what we're clicking
    console.log("[stepGenerate] clicking button:", targetBtn.textContent?.trim().slice(0, 40), "disabled:", targetBtn.disabled);

    targetBtn.click();
    return { ok: true, data: { count: btns.length, clicked: targetBtn.textContent?.trim().slice(0, 40) }, error: null };
  }

  // ---------------------------------------------------------------------------
  // Step 8: Wait for stable images
  // ---------------------------------------------------------------------------
  async function stepWait(job) {
    const deadline = Date.now() + (job.timeoutSeconds ? job.timeoutSeconds * 1000 : 600000);
    let stableSince = 0;
    let lastKeys = [];
    let resultImages = [];

    const baselineKeys = new Set();
    for (const img of document.querySelectorAll("img")) {
      if (img.src) baselineKeys.add(img.src);
    }

    while (Date.now() < deadline) {
      const currentImgs = Array.from(document.querySelectorAll("img")).filter(img => {
        if (!isVisible(img)) return false;
        if (baselineKeys.has(img.src)) return false;
        const rect = img.getBoundingClientRect();
        return rect.width > 100 && rect.height > 100;
      });

      if (currentImgs.length > 0) {
        const currentKeys = currentImgs.map(img => img.src).sort();
        const sameAsPrevious = currentKeys.length === lastKeys.length && currentKeys.every((k, i) => k === lastKeys[i]);
        if (sameAsPrevious) {
          if (!stableSince) stableSince = Date.now();
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

    if (resultImages.length === 0) return { ok: false, data: null, error: "Timed out waiting for images" };
    return { ok: true, data: { images: resultImages.slice(0, 4) }, error: null };
  }

  // ---------------------------------------------------------------------------
  // Export to window (shared across all content scripts)
  // ---------------------------------------------------------------------------
  window.stepNav = stepNav;
  window.stepTab = stepTab;
  window.stepModel = stepModel;
  window.stepRatio = stepRatio;
  window.stepUpload = stepUpload;
  window.stepPrompt = stepPrompt;
  window.stepGenerate = stepGenerate;
  window.stepWait = stepWait;
})();
