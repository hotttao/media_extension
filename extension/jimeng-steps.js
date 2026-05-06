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
      console.log(`  listbox[${i}] text:${lb.textContent.trim().slice(0,40)} role-option-count:${opts.length}`);
      // Also log direct children as fallback
      const children = Array.from(lb.children || []);
      console.log(`  listbox[${i}] direct-children:${children.length}`);
      children.forEach((c, j) => console.log(`    child[${j}]: tag=${c.tagName} text="${c.textContent?.trim().slice(0,30)}" aria="${c.getAttribute("aria-label") || ""}"`));
    });

    // Try role="option" first, then fall back to all clickable children of listbox
    let options = Array.from(document.querySelectorAll('[role="option"]'));
    console.log("[stepModel] role=option count:", options.length);

    // Helper: get display text from an option element
    const optionDisplayText = (el) => {
      const direct = el.textContent?.trim() || "";
      if (direct) return direct;
      return el.getAttribute("aria-label") || "";
    };

    // If no role=option elements, search listbox children directly
    if (options.length === 0 && listboxes.length > 0) {
      console.log("[stepModel] no role=option found, searching listbox children directly");
      const allClickable = [];
      listboxes.forEach(lb => {
        Array.from(lb.querySelectorAll("*")).forEach(el => {
          const tag = el.tagName?.toUpperCase();
          if (tag === "LI" || tag === "BUTTON" || tag === "DIV" || el.getAttribute("role") === "option") {
            const text = optionDisplayText(el);
            if (text || isVisible(el)) {
              allClickable.push(el);
              console.log(`[stepModel] clickable child: tag=${tag} text="${text.slice(0,30)}"`);
            }
          }
        });
      });
      options = allClickable;
    }

    // Fuzzy: prefer "Lite" option, fall back to any model option with version number
    let targetOption = options.find(el => optionDisplayText(el).includes("Lite"));
    if (!targetOption) {
      targetOption = options.find(el => /[\d]+\.[\d]+/.test(optionDisplayText(el)));
    }
    if (!targetOption && options.length > 0) {
      // Last resort: first visible, non-empty option
      targetOption = options.find(el => isVisible(el) && optionDisplayText(el));
    }
    if (!targetOption && options.length > 0) {
      targetOption = options[0];
    }
    if (!targetOption) {
      const optionSummaries = options.map((o, i) => `${i}:text="${optionDisplayText(o).slice(0,20)}"`).join(" | ");
      throw new Error(`No selectable model option found (options: ${optionSummaries || "NONE"})`);
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

    // Open modal by clicking a grid thumbnail, wait for it to appear
    const openModal = (gridThumb) => {
      return new Promise((resolve) => {
        document.body.click(); // close any open modal
        gridThumb.click();
        let attempts = 0;
        const maxWait = 60;
        const check = setInterval(() => {
          attempts++;
          const modal = document.querySelector(".lv-modal-wrapper");
          if (modal) { clearInterval(check); setTimeout(() => resolve(modal), 800); }
          else if (attempts >= maxWait) { clearInterval(check); resolve(null); }
        }, 500);
      });
    };

    // Find thumbnail switcher images inside an open modal (top-right scroll container)
    const getModalThumbs = (modal) => {
      const scroll = modal.querySelector('[class*="scroll-container"]');
      if (!scroll) return [];
      return Array.from(scroll.querySelectorAll("img")).filter(img => {
        if (!img.src || img.src.startsWith("data:") || img.src.startsWith("blob:")) return false;
        if (!img.src.includes("byteimg.com")) return false;
        if (img.src.includes("mosaic") || img.src.includes("avatar")) return false;
        return true;
      });
    };

    // Wait for HD image in open modal (first CDN img with w > 300)
    const pollModalHd = (modal) => {
      return new Promise((resolve) => {
        let attempts = 0;
        const maxAttempts = 90;
        const interval = setInterval(() => {
          attempts++;
          const imgs = Array.from(modal.querySelectorAll("img"));
          const hd = imgs.find(img => {
            try { return img.getBoundingClientRect().width > 300 && img.src.startsWith("http") && !img.src.startsWith("data:") && !img.src.startsWith("blob:"); }
            catch { return false; }
          });
          if (hd) { clearInterval(interval); resolve(hd.src); }
          else if (attempts >= maxAttempts) { clearInterval(interval); resolve(null); }
        }, 500);
      });
    };

    // Click grid thumbnail -> open modal -> click each modal thumbnail to switch images
    // Returns array of HD URLs captured from this grid thumbnail's modal
    const captureModalImages = (gridThumb) => {
      return new Promise(async (resolve) => {
        const modal = await openModal(gridThumb);
        if (!modal) { resolve([]); return; }

        const modalThumbs = getModalThumbs(modal);
        const captured = [];

        if (modalThumbs.length === 0) {
          // No thumbnail switcher - just capture the one image in modal
          const hd = await pollModalHd(modal);
          if (hd) captured.push(hd);
          document.body.click();
          resolve(captured);
          return;
        }

        // Click each modal thumbnail to switch to a different image
        for (let i = 0; i < modalThumbs.length; i++) {
          modalThumbs[i].click();
          await delay(1200); // wait for image to switch in modal
          const hd = await pollModalHd(modal);
          if (hd) captured.push(hd);
          if (captured.length >= 4) break;
        }

        document.body.click();
        resolve(captured);
      });
    };


    // Main loop: collect up to 4 HD images by clicking each thumbnail in order
    const resultUrls = [];
    let tryIndex = 0;

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
      console.log("[stepWait] clicking grid thumbnail[" + tryIndex + "], src=" + (target ? target.src.slice(0, 50) : "null"));

      try {
        const urls = await captureModalImages(target);
        if (urls.length > 0) {
          urls.forEach(url => { resultUrls.push(url); });
          console.log("[stepWait] captured", urls.length, "from modal, total:", resultUrls.length);
          if (resultUrls.length >= 4) break;
        }
        tryIndex++; // move to next grid thumbnail
      } catch(e) {
        console.log("[stepWait] card", tryIndex, "error:", e.message);
        document.body.click();
        tryIndex++;
        await delay(2000);
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
  // Jimeng Video Steps
  // ---------------------------------------------------------------------------

  // S1V: Navigate to jimeng video URL
  async function stepVideoNav(targetUrl) {
    if (window.location.href !== targetUrl) {
      window.location.href = targetUrl;
      return { ok: true, data: { status: "navigating" }, error: null };
    }
    return { ok: true, data: { status: "already_on_page", url: window.location.href }, error: null };
  }

  // S2V: Click "视频生成" tab (skip if already on type=video page)
  async function stepVideoTab() {
    if (window.location.href.includes("type=video")) {
      try {
        await waitFor(() => document.querySelector('[role="combobox"]'), { timeoutMs: 15000, label: "combobox" });
        return { ok: true, data: { status: "already_on_video_tab" }, error: null };
      } catch {
        return { ok: false, data: null, error: "type=video page loaded but combobox not found" };
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
          if (el.childNodes.length === 1 && textLike(el.textContent, "视频生成")) {
            el.click(); return true;
          }
        }
        return false;
      });
      if (!clicked) return { ok: false, data: null, error: "视频生成 tab not found" };
      await delay(1000);
      await waitFor(() => window.location.href.includes("type=video"), { timeoutMs: 15000, label: "type=video URL" });
      await waitFor(() => document.querySelector('[role="combobox"]'), { timeoutMs: 15000, label: "combobox" });
      return { ok: true, data: { status: "clicked_via_evaluate" }, error: null };
    }

    const parentClickable = tab.parentElement;
    const isMenuItem = parentClickable && (parentClickable.getAttribute("role")?.includes("menu") ||
      parentClickable.className?.includes("menu") || parentClickable.tagName === "LI");

    if (!isMenuItem && textLike(tab.textContent, "视频生成")) {
      const parentVisible = parentClickable && isVisible(parentClickable);
      if (parentVisible) {
        parentClickable.click();
        await delay(1000);
        const secondClick = Array.from(document.querySelectorAll("*")).find(el =>
          textLike(el.textContent, "视频生成") && isVisible(el) && el !== tab
        );
        if (secondClick) { secondClick.click(); }
        await waitFor(() => window.location.href.includes("type=video"), { timeoutMs: 15000, label: "type=video URL" });
        return { ok: true, data: { status: "parent_then_option", parentTag: parentClickable.tagName }, error: null };
      }
      tab.click();
      await delay(1000);
      const option = Array.from(document.querySelectorAll("*")).find(el =>
        textLike(el.textContent, "视频生成") && isVisible(el) && el !== tab
      );
      if (option) { option.click(); }
      await waitFor(() => window.location.href.includes("type=video"), { timeoutMs: 15000, label: "type=video URL" });
      return { ok: true, data: { status: "trigger_then_option" }, error: null };
    }

    tab.click();
    await waitFor(() => window.location.href.includes("type=video"), { timeoutMs: 15000, label: "type=video URL" });
    return { ok: true, data: { status: "menu_item_clicked" }, error: null };
  }

  // S3V: Select Seedance model
  async function stepVideoModel() {
    const delayMs = 500;

    try {
      await waitFor(() => document.querySelector('[role="combobox"]'), { timeoutMs: 20000, label: "model_combobox" });
    } catch {
      const comboboxes = Array.from(document.querySelectorAll('[role="combobox"]'));
      const comboboxTexts = comboboxes.map(el => el.textContent?.trim().slice(0, 30)).join(" | ");
      throw new Error(`Model combobox not found (timed out, found: ${comboboxTexts})`);
    }

    const comboboxes = Array.from(document.querySelectorAll('[role="combobox"]'));
    const modelCombobox = comboboxes.find(el =>
      textIncludes(el.textContent || "", "Seedance")
    );
    if (!modelCombobox) {
      const comboboxTexts = comboboxes.map(el => el.textContent?.trim().slice(0, 30)).join(" | ");
      throw new Error(`Seedance combobox not found (found: ${comboboxTexts})`);
    }

    let listbox = null;
    for (let attempt = 0; attempt < 3; attempt++) {
      modelCombobox.click();
      await delay(delayMs);
      const allListboxes = Array.from(document.querySelectorAll('[role="listbox"]'));
      listbox = allListboxes.find(lb => textIncludes(lb.textContent || "", "Seedance"));
      if (listbox) break;
      document.body.click();
      await delay(300);
    }
    if (!listbox) {
      const allListboxes = Array.from(document.querySelectorAll('[role="listbox"]')).map(el => el.textContent?.trim().slice(0, 40)).join(" | ");
      throw new Error(`Seedance listbox not visible after combobox click (found: ${allListboxes || "none"})`);
    }

    const options = Array.from(listbox.querySelectorAll('[role="option"]'));
    const targetOption = options.find(el => textIncludes(el.textContent || "", "Seedance"));
    if (!targetOption) {
      // Already default-selected
      document.body.click();
      await delay(300);
      return { ok: true, data: { status: "model_already_selected" }, error: null };
    }

    targetOption.click();
    await delay(delayMs);
    document.body.click();
    await delay(300);
    return { ok: true, data: { modelText: modelCombobox.textContent?.trim() || "" }, error: null };
  }

  // S4V: Select aspect ratio
  async function stepVideoRatio(job) {
    const ratio = job.aspectRatio || "16:9";
    if (ratio === "16:9") {
      return { ok: true, data: { ratio: "16:9", status: "default_ratio" }, error: null };
    }

    const delayMs = 500;
    const allButtons = () => Array.from(document.querySelectorAll("button")).filter(isVisible);

    const ratioBtn = allButtons().find(el => /\d+:\d+/.test(el.textContent || ""));
    if (!ratioBtn) {
      const allBtns = allButtons().map(el => el.textContent?.trim().slice(0, 40)).join(" | ");
      throw new Error(`Ratio button not found (buttons: ${allBtns})`);
    }

    ratioBtn.click();
    await delay(delayMs);

    const ratioLabel = Array.from(document.querySelectorAll("label.lv-radio")).find(el =>
      textLike(el.textContent?.trim(), ratio)
    );
    if (!ratioLabel) {
      const allLabels = Array.from(document.querySelectorAll("label.lv-radio")).map(l => l.textContent?.trim()).join(" | ");
      throw new Error(`Ratio ${ratio} not found in dropdown (found: ${allLabels})`);
    }

    ratioLabel.click();
    await delay(200);
    document.body.click();
    await delay(300);
    return { ok: true, data: { ratio }, error: null };
  }

  // S5V: Upload first-frame image
  async function stepVideoUploadFirstFrame(asset) {
    if (!asset) return { ok: true, data: { status: "skipped", reason: "no_asset" }, error: null };

    const delayMs = 500;

    // Find zone containing "首帧"
    let zone = null;
    for (const el of document.querySelectorAll("[class*='reference-item']")) {
      if (textIncludes(el.textContent || "", "首帧") && isVisible(el)) {
        zone = el;
        break;
      }
    }
    if (!zone) {
      // Try broader search
      for (const el of document.querySelectorAll("*")) {
        if (textIncludes(el.textContent || "", "首帧") && isVisible(el) && el.querySelector("input[type='file']")) {
          zone = el; break;
        }
      }
    }
    if (!zone) return { ok: true, data: { status: "skipped", reason: "no_first_frame_zone" }, error: null };

    const fileInput = zone.querySelector("input[type='file']");
    if (!fileInput) return { ok: true, data: { status: "skipped", reason: "no_file_input_in_zone" }, error: null };

    const response = await bridgeFetch({ url: asset.url, responseType: "blobBase64" });
    const binary = atob(response.base64Data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const mimeType = asset.mimeType || response.mimeType || "application/octet-stream";
    const file = new File([bytes], asset.name, { type: mimeType });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    fileInput.files = transfer.files;
    fileInput.dispatchEvent(new Event("change", { bubbles: true }));

    // Wait for preview image to appear (img width > 50, not data:/blob:)
    await waitFor(() => {
      const imgs = zone.querySelectorAll("img");
      return Array.from(imgs).find(img => {
        try { return img.getBoundingClientRect().width > 50 && !img.src.startsWith("data:") && !img.src.startsWith("blob:"); } catch { return false; }
      }) || null;
    }, { timeoutMs: 15000, label: "first_frame_preview" });

    return { ok: true, data: { status: "uploaded", name: asset.name }, error: null };
  }

  // S6V: Upload last-frame image
  async function stepVideoUploadLastFrame(asset) {
    if (!asset) return { ok: true, data: { status: "skipped", reason: "no_asset" }, error: null };

    const delayMs = 500;

    // Find zone containing "尾帧"
    let zone = null;
    for (const el of document.querySelectorAll("[class*='reference-item']")) {
      if (textIncludes(el.textContent || "", "尾帧") && isVisible(el)) {
        zone = el; break;
      }
    }
    if (!zone) {
      for (const el of document.querySelectorAll("*")) {
        if (textIncludes(el.textContent || "", "尾帧") && isVisible(el) && el.querySelector("input[type='file']")) {
          zone = el; break;
        }
      }
    }
    if (!zone) return { ok: true, data: { status: "skipped", reason: "no_last_frame_zone" }, error: null };

    const fileInput = zone.querySelector("input[type='file']");
    if (!fileInput) return { ok: true, data: { status: "skipped", reason: "no_file_input_in_zone" }, error: null };

    const response = await bridgeFetch({ url: asset.url, responseType: "blobBase64" });
    const binary = atob(response.base64Data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const mimeType = asset.mimeType || response.mimeType || "application/octet-stream";
    const file = new File([bytes], asset.name, { type: mimeType });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    fileInput.files = transfer.files;
    fileInput.dispatchEvent(new Event("change", { bubbles: true }));

    await waitFor(() => {
      const imgs = zone.querySelectorAll("img");
      return Array.from(imgs).find(img => {
        try { return img.getBoundingClientRect().width > 50 && !img.src.startsWith("data:") && !img.src.startsWith("blob:"); } catch { return false; }
      }) || null;
    }, { timeoutMs: 15000, label: "last_frame_preview" });

    return { ok: true, data: { status: "uploaded", name: asset.name }, error: null };
  }

  // S7V: Fill prompt and movement textareas
  async function stepVideoPrompt(job) {
    const delayMs = 300;

    const promptEls = () => {
      const results = [];
      for (const el of document.querySelectorAll("textarea")) {
        if (isVisible(el)) results.push(el);
      }
      return results;
    };

    // Find textarea with placeholder containing "运动方式"
    const movementTextarea = promptEls().find(el =>
      textIncludes(el.getAttribute("placeholder") || "", "运动方式")
    );
    const promptTextarea = promptEls().find(el =>
      el !== movementTextarea && textIncludes(el.getAttribute("placeholder") || "", "描述")
    );

    if (movementTextarea) {
      movementTextarea.focus();
      movementTextarea.value = "";
      movementTextarea.value = job.movement || job.prompt || "";
      movementTextarea.dispatchEvent(new InputEvent("input", { bubbles: true, data: job.movement || job.prompt }));
      movementTextarea.dispatchEvent(new Event("change", { bubbles: true }));
      await delay(delayMs);
    }

    if (promptTextarea) {
      promptTextarea.focus();
      promptTextarea.value = "";
      promptTextarea.value = job.prompt || "";
      promptTextarea.dispatchEvent(new InputEvent("input", { bubbles: true, data: job.prompt }));
      promptTextarea.dispatchEvent(new Event("change", { bubbles: true }));
      await delay(delayMs);
    } else if (promptEls().length >= 2) {
      // Fallback: fill first visible textarea with movement/prompt, second with prompt
      const all = promptEls();
      all[0].focus();
      all[0].value = "";
      all[0].value = job.movement || job.prompt || "";
      all[0].dispatchEvent(new InputEvent("input", { bubbles: true }));
      all[0].dispatchEvent(new Event("change", { bubbles: true }));
      await delay(delayMs);
      all[1].focus();
      all[1].value = "";
      all[1].value = job.prompt || "";
      all[1].dispatchEvent(new InputEvent("input", { bubbles: true }));
      all[1].dispatchEvent(new Event("change", { bubbles: true }));
      await delay(delayMs);
    } else if (promptEls().length === 1) {
      // Only one textarea found, fill it with prompt
      const el = promptEls()[0];
      el.focus();
      el.value = "";
      el.value = job.prompt || "";
      el.dispatchEvent(new InputEvent("input", { bubbles: true, data: job.prompt }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      await delay(delayMs);
    }

    return { ok: true, data: { promptLength: (job.prompt || "").length, movementLength: (job.movement || "").length }, error: null };
  }

  // S8V: Click generate button
  async function stepVideoGenerate() {
    const delayMs = 200;

    const enabledBtn = await waitFor(() => {
      const btn = document.querySelector("button.lv-btn-primary:not([disabled])");
      return btn || null;
    }, { timeoutMs: 300000, label: "lv-btn-primary_enabled" });

    const targetBtn = await enabledBtn;
    if (!targetBtn) {
      const allBtns = Array.from(document.querySelectorAll("button")).slice(0, 8).map(b =>
        `dis:${b.disabled} cls:${b.className.replace(/\S+/g, m => m).slice(0, 35)}`
      ).join(" | ");
      throw new Error(`Generate button never became enabled (all_btns: ${allBtns})`);
    }

    console.log("[stepVideoGenerate] clicking:", targetBtn.className.slice(0, 40));
    targetBtn.click();
    await delay(delayMs);

    const isProcessing = document.querySelector("button.lv-btn-primary:disabled") !== null;
    console.log("[stepVideoGenerate] clicked, processing:", isProcessing);
    return { ok: true, data: { clicked: targetBtn.className.slice(0, 30), processing: isProcessing }, error: null };
  }

  // S9V: Wait for generated video
  async function stepVideoWait(job) {
    const TIMEOUT_MS = (job.timeoutSeconds ? job.timeoutSeconds : 600) * 1000;
    const deadline = Date.now() + TIMEOUT_MS;
    const POLL_INTERVAL_MS = 3000;

    // Wait for /generate navigation
    if (!window.location.href.includes("/generate")) {
      console.log("[stepVideoWait] waiting for /generate navigation...");
      const navDeadline = Date.now() + 60000;
      while (Date.now() < navDeadline) {
        if (window.location.href.includes("/generate")) {
          console.log("[stepVideoWait] navigated to:", window.location.href);
          break;
        }
        await delay(500);
      }
    }

    console.log("[stepVideoWait] START, deadline in", Math.round((deadline - Date.now()) / 1000), "s at:", window.location.href);

    // Helper: poll for stable video source
    const pollForStableVideo = async () => {
      let lastSrc = "";
      let stableCount = 0;
      const STABLE_THRESHOLD = 8; // seconds stable

      while (Date.now() < deadline) {
        // Try video element first
        const videoEl = document.querySelector("video");
        if (videoEl && videoEl.src && !videoEl.src.startsWith("data:") && !videoEl.src.startsWith("blob:") && videoEl.src === lastSrc) {
          stableCount += POLL_INTERVAL_MS / 1000;
          if (stableCount >= STABLE_THRESHOLD) {
            return { videoUrl: videoEl.src, sourceType: "videoElement" };
          }
        } else if (videoEl && videoEl.src) {
          lastSrc = videoEl.src;
          stableCount = 0;
        }

        // Try download link (a[href*=".mp4"])
        const downloadLink = document.querySelector("a[href*='.mp4']");
        if (downloadLink && downloadLink.href && downloadLink.href === lastSrc) {
          stableCount += POLL_INTERVAL_MS / 1000;
          if (stableCount >= STABLE_THRESHOLD) {
            return { videoUrl: downloadLink.href, sourceType: "downloadLink" };
          }
        } else if (downloadLink && downloadLink.href) {
          lastSrc = downloadLink.href;
          stableCount = 0;
        }

        await delay(POLL_INTERVAL_MS);
      }
      return null;
    };

    // Try polling approach first
    const pollResult = await pollForStableVideo();
    if (pollResult) {
      console.log("[stepVideoWait] video found via polling:", pollResult.sourceType);
      return { ok: true, data: pollResult, error: null };
    }

    // Fallback: look for "去查看" button and click it, then wait for video element
    const viewBtn = Array.from(document.querySelectorAll("a, button")).find(el =>
      textIncludes(el.textContent || "", "去查看")
    );
    if (viewBtn) {
      console.log("[stepVideoWait] clicking '去查看' button");
      viewBtn.click();
      await delay(2000);

      const videoEl = await waitFor(() => {
        const v = document.querySelector("video");
        return (v && v.src && !v.src.startsWith("data:") && !v.src.startsWith("blob:")) ? v : null;
      }, { timeoutMs: 30000, label: "video_element_after_view" });

      if (videoEl) {
        // Wait for video to be stable
        let lastSrc = "";
        let stableCount = 0;
        while (Date.now() < deadline && stableCount < 8) {
          if (videoEl.src === lastSrc && lastSrc !== "") {
            stableCount += 1;
          } else {
            lastSrc = videoEl.src;
            stableCount = 0;
          }
          await delay(1000);
        }
        return { ok: true, data: { videoUrl: videoEl.src, sourceType: "videoElement" }, error: null };
      }
    }

    return { ok: false, data: null, error: `Timed out after ${job.timeoutSeconds || 600}s, no video found` };
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
  window.stepVideoNav = stepVideoNav;
  window.stepVideoTab = stepVideoTab;
  window.stepVideoModel = stepVideoModel;
  window.stepVideoRatio = stepVideoRatio;
  window.stepVideoUploadFirstFrame = stepVideoUploadFirstFrame;
  window.stepVideoUploadLastFrame = stepVideoUploadLastFrame;
  window.stepVideoPrompt = stepVideoPrompt;
  window.stepVideoGenerate = stepVideoGenerate;
  window.stepVideoWait = stepVideoWait;
})();
