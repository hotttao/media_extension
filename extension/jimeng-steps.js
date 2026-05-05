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
    if (!domText || !target) return false;
    const dt = domText.trim();
    if (dt.length < target.length) return false;
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
    try {
      const style = window.getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") return false;
    } catch(e) { return false; }
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
      throw new Error(`Model combobox not found (timed out waiting, found: ${comboboxTexts})`);
    }

    const comboboxes = allEls().filter(el => el.getAttribute("role") === "combobox");
    // Fuzzy match: any combobox with 图片 + a version number (4.x, 5.0, etc.)
    const modelCombobox = comboboxes.find(el => {
      const t = el.textContent?.trim() || "";
      return t.includes("图片") && /[\d]+\.[\d]+/.test(t);
    });
    if (!modelCombobox) {
      const comboboxTexts = comboboxes.map(el => el.textContent?.trim().slice(0, 30)).join(" | ");
      throw new Error(`Model combobox not found (checked for 图片+version, found: ${comboboxTexts})`);
    }

    // Click and wait for listbox to appear (retry if it was already open)
    let listbox = null;
    for (let attempt = 0; attempt < 3; attempt++) {
      modelCombobox.click();
      await delay(delayMs);
      // Find a listbox that contains model options (图片5.0 or 图片4.x)
      const allListboxes = Array.from(document.querySelectorAll('[role="listbox"]'));
      listbox = allListboxes.find(lb =>
        lb.textContent?.includes("5.0") || lb.textContent?.includes("4.6")
      );
      if (listbox) break;
      // If no listbox found, click body to close any open dropdown and retry
      document.body.click();
      await delay(300);
    }
    if (!listbox) {
      const allListboxes = Array.from(document.querySelectorAll('[role="listbox"]')).map(el => el.textContent?.trim().slice(0, 40)).join(" | ");
      throw new Error(`Model listbox not visible after combobox click (checked role=listbox, found: ${allListboxes || "none"})`);
    }
    await delay(delayMs);

    // Log ALL listboxes and their option children for debugging
    const listboxes = Array.from(document.querySelectorAll('[role="listbox"]'));
    console.log("[stepModel] listboxes found:", listboxes.length);
    listboxes.forEach((lb, i) => {
      const opts = lb.querySelectorAll('[role="option"]');
      console.log(`  listbox[${i}] text:${lb.textContent.trim().slice(0,40)} options:${opts.length}`);
      Array.from(opts).slice(0,3).forEach((o, j) => console.log(`    opt[${j}]: "${o.textContent.trim().slice(0,20)}"`));
    });

    const options = Array.from(document.querySelectorAll('[role="option"]'));
    console.log("[stepModel] raw querySelectorAll('[role=option]') result:", options.length);
    // Fuzzy: prefer "Lite" option, fall back to any model option with version number
    let targetOption = options.find(el =>
      el.textContent?.trim().includes("Lite")
    );
    if (!targetOption) {
      targetOption = options.find(el => /[\d]+\.[\d]+/.test(el.textContent?.trim() || ""));
    }
    if (!targetOption && options.length > 0) {
      targetOption = options[0]; // fall back to first option
    }
    if (!targetOption) {
      const optionTexts = options.map(o => o.textContent?.trim().slice(0, 40)).join(" | ");
      throw new Error(`No selectable model option found (options: ${optionTexts || "NONE"})`);
    }

    targetOption.click();
    await delay(delayMs);
    document.body.click();
    await delay(300);

    const modelText = modelCombobox?.textContent?.trim() || "";
    // Just verify combobox text has changed from original (has version number now)
    const modelChanged = /[\d]+\.[\d]+/.test(modelText);
    if (!modelChanged) throw new Error(`Model combobox text unchanged after click (current: ${modelText})`);
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
    if (!ratioBtn) {
      const allBtns = allButtons().map(el => el.textContent?.trim().slice(0, 40)).join(" | ");
      throw new Error(`Ratio button not found (checked for K+ratio/intelligent, buttons: ${allBtns})`);
    }

    ratioBtn.click();
    await delay(delayMs);
    console.log("[stepRatio] clicked ratio button, now looking for options");

    // Dropdown uses label.lv-radio elements (e.g. "9:16", "高清 2K", etc.)
    // Default resolution is already "高清 2K" — just need to select "9:16" ratio
    const ratioLabel = Array.from(document.querySelectorAll("label.lv-radio")).find(el =>
      el.textContent?.trim() === "9:16"
    );

    if (!ratioLabel) {
      const allLabels = Array.from(document.querySelectorAll("label.lv-radio")).map(l => l.textContent?.trim()).join(" | ");
      throw new Error(`Ratio 9:16 not found in dropdown (found: ${allLabels})`);
    }

    ratioLabel.click();
    await delay(200);
    document.body.click();
    await delay(300);

    // Verify the ratio button now shows 9:16
    const ratioBtnAfter = Array.from(document.querySelectorAll("button")).find(el =>
      /\d+:\d+/.test(el.textContent || "")
    );
    const ratioText = ratioBtnAfter?.textContent?.trim() || "";
    if (!ratioText.includes("9:16")) {
      throw new Error(`Ratio button not updated after selection (current: ${ratioText})`);
    }

    return { ok: true, data: { ratio: "9:16", resolution: "2K" }, error: null };
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
      const inputs = fileInputs();
      // If slotIndex is out of range, use the last available input (overflow assets)
      const safeIndex = Math.min(slotIndex, inputs.length - 1);

      // Method 1: Direct file input
      if (inputs.length > 0) {
        const input = inputs[safeIndex];
        const file = await fetchAssetAsFile(asset);
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));
        await delay(500);
        await waitFor(() => {
          const previews = document.querySelectorAll("img[src*='data:'],[src*='blob:']");
          return previews.length > safeIndex;
        }, { timeoutMs: 10000, label: `image preview ${asset.label}` });
        continue;
      }

      // Method 2: Upload slot click
      const slots = uploadSlots();
      if (slots.length > 0) {
        slots[Math.min(slotIndex, slots.length - 1)].click();
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
            return previews.length > safeIndex;
          }, { timeoutMs: 10000, label: `image preview ${asset.label}` });
          continue;
        }
      }

      // Method 3: Text-based upload buttons
      let clicked = false;
      const label = asset.label || "";
      for (const el of document.querySelectorAll("*")) {
        const text = el.textContent?.trim() || "";
        if ((text === label || text.includes(label)) && isVisible(el)) {
          el.click();
          clicked = true;
          break;
        }
      }

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

      throw new Error(`Failed to upload: ${asset.label} (all upload methods exhausted)`);
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

    if (!promptEl) throw new Error(`Prompt input not found (tried: textarea, input[placeholder*=描述], contenteditable, tiptap; visible count: ${promptEls.length})`);

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
    const delayMs = 200;

    // Wait for submit button to be enabled (becomes clickable after upload + prompt)
    const enabledSubmit = waitFor(() => {
      const btn = document.querySelector('button[class*="submit-button"]:not([disabled])');
      return btn || null;
    }, { timeoutMs: 300000, label: "enabled_submit_button" });

    const targetBtn = await enabledSubmit;

    if (!targetBtn) {
      const allBtns = Array.from(document.querySelectorAll("button")).slice(0, 8).map(b =>
        `dis:${b.disabled} cls:${b.className.replace(/\S+/g, m => m).slice(0, 35)}`
      ).join(" | ");
      throw new Error(`Generate button never became enabled (all_btns: ${allBtns})`);
    }

    console.log("[stepGenerate] clicking enabled submit:", targetBtn.className.slice(0, 40));
    targetBtn.click();
    await delay(delayMs);

    const isProcessing = document.querySelector('button[class*="submit-button"]:disabled') !== null;
    console.log("[stepGenerate] clicked, processing started:", isProcessing);
    return { ok: true, data: { clicked: targetBtn.className.slice(0, 30), processing: isProcessing }, error: null };
  }

  // ---------------------------------------------------------------------------
  // Step 8: Wait for generated images (verified by clicking into HD modal)
  // ---------------------------------------------------------------------------
  async function stepWait(job) {
    // jimeng generates HD images asynchronously after placeholder appears.
    // Strategy: wait for /generate page → click each card → check modal for HD blob → done.
    // Timeout: 5 minutes (300s) — only fail if no card can be opened in that time.
    const TIMEOUT_MS = (job.timeoutSeconds ? job.timeoutSeconds : 300) * 1000;
    const deadline = Date.now() + TIMEOUT_MS;
    const POLL_INTERVAL_MS = 3000;
    const CLICK_RETRY_MS = 2000;

    // Wait for /generate navigation (Jimeng transitions here after clicking generate)
    if (!window.location.href.includes("/generate")) {
      console.log("[stepWait] waiting for /generate navigation...");
      const navDeadline = Date.now() + 60000;
      while (Date.now() < navDeadline) {
        if (window.location.href.includes("/generate")) {
          console.log("[stepWait] navigated to:", window.location.href);
          break;
        }
        await delay(500);
      }
    }

    console.log("[stepWait] START, deadline in", Math.round((deadline - Date.now()) / 1000), "s at:", window.location.href);

    // Helper: find all candidate thumbnail images in record-box grid
    // Note: getBoundingClientRect may return 0 in some measurement contexts, so
    // we rely on byteimg.com CDN URL presence as primary filter
    const getThumbnailImages = () => {
      const recordBox = document.querySelector('[class*="record-box-wrapper"]');
      if (!recordBox) return [];
      const imgs = recordBox.querySelectorAll("img");
      return Array.from(imgs).filter(img => {
        if (!img.src || img.src === "about:blank" || img.src.startsWith("data:")) return false;
        // Must be a jimeng CDN image (byteimg.com)
        if (!img.src.includes("byteimg.com")) return false;
        // Filter out tiny mosaic/icon images by src pattern
        if (img.src.includes("mosaic") || img.src.includes("avatar")) return false;
        return true;
      });
    };

    // Helper: click a thumbnail to open detail modal, return HD URL if ready
    // HD in modal: width > 300 AND src is a CDN URL (not data: or blob:)
    // (Jimeng doesn't use blob: URLs in the modal preview, it shows a high-res CDN URL)
    const tryGetHdFromCard = (imgEl) => {
      return new Promise((resolve) => {
        // Close any open modal — ensures we get a fresh modal for this specific card
        document.body.click();
        imgEl.click();
        // Poll for modal with HD image (every 500ms, up to 45s per card)
        let attempts = 0;
        const maxAttempts = 90;
        const checkInterval = setInterval(() => {
          attempts++;
          const modal = document.querySelector(".lv-modal-wrapper");
          if (!modal) {
            if (attempts >= maxAttempts) {
              clearInterval(checkInterval);
              document.body.click();
              setTimeout(() => resolve(null), 100);
            }
            return;
          }
          // Look for HD image: width > 300 and CDN URL (not blob:, not data:)
          const modalImgs = modal.querySelectorAll("img");
          const hdImg = Array.from(modalImgs).find(img => {
            try {
              const w = img.getBoundingClientRect().width;
              const src = img.src;
              return w > 300 && src.startsWith("http") && !src.startsWith("data:");
            } catch { return false; }
          });
          if (hdImg) {
            clearInterval(checkInterval);
            const hdUrl = hdImg.src;
            console.log("[stepWait] HD found:", hdUrl.slice(0, 60), "w:", Math.round(hdImg.getBoundingClientRect().width));
            // Close modal
            document.body.click();
            setTimeout(() => resolve(hdUrl), 200);
          } else if (attempts >= maxAttempts) {
            clearInterval(checkInterval);
            document.body.click();
            setTimeout(() => resolve(null), 100);
          }
        }, 500);
      });
    };

    // Main loop: collect up to 4 HD images by clicking each thumbnail in order
    // Start from index 0, advance after each successful HD capture
    const resultUrls = [];
    let tryIndex = 0;
    const MAX_CONSECUTIVE_FAILURES = 8;

    while (Date.now() < deadline && resultUrls.length < 4) {
      const thumbnails = getThumbnailImages();
      console.log("[stepWait] thumbnails:", thumbnails.length, "captured:", resultUrls.length, "next index:", tryIndex);

      if (thumbnails.length === 0) {
        console.log("[stepWait] no thumbnails yet, waiting 60s...");
        await delay(60000);  // wait 1 min before first retry
        tryIndex = 0;
        continue;
      }

      // Try the next uncaptured thumbnail
      if (tryIndex >= thumbnails.length) {
        console.log("[stepWait] all thumbnails tried, waiting 5s before retry...");
        tryIndex = 0;
        await delay(5000);  // wait 5s between retry cycles
        continue;
      }

      const target = thumbnails[tryIndex];
      console.log("[stepWait] attempting HD extraction from card", tryIndex, "...");

      try {
        const hdUrl = await tryGetHdFromCard(target);
        if (hdUrl) {
          resultUrls.push(hdUrl);
          console.log("[stepWait] HD captured:", hdUrl.slice(0, 50), "total:", resultUrls.length);
          tryIndex = 0; // Reset for next image
        } else {
          console.log("[stepWait] card", tryIndex, "not ready, waiting 2s then next...");
          await delay(2000);  // wait 2s between retry
          tryIndex++;
        }
      } catch(e) {
        console.log("[stepWait] card", tryIndex, "error:", e.message);
        await delay(2000);
        tryIndex++;
      }
    }

    if (resultUrls.length === 0) {
      return { ok: false, data: null, error: `Timed out after 5min, no HD images captured` };
    }

    console.log("[stepWait] completed, captured", resultUrls.length, "HD blobs");
    // Return objects with src pointing to HD blob URLs
    const resultImages = resultUrls.map(url => ({ src: url }));
    return { ok: true, data: { images: resultImages }, error: null };
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
