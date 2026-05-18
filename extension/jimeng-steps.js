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

  const waitFor = async (predicate, options = {}) => {
    const timeoutMs = options.timeoutMs ?? 120000;
    const intervalMs = options.intervalMs ?? 250;
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const value = await predicate();
      if (value) return value;
      await delay(intervalMs);
    }
    throw new Error(`Timed out waiting for ${options.label || "condition"}`);
  };

  const clickElement = (el) => {
    if (!el) return false;
    try { el.scrollIntoView({ block: "center", inline: "center" }); } catch (_error) {}
    const eventInit = { bubbles: true, cancelable: true, view: window };
    for (const type of ["pointerdown", "mousedown", "mouseup", "pointerup"]) {
      try { el.dispatchEvent(new MouseEvent(type, eventInit)); } catch (_error) {}
    }
    try {
      el.click();
      return true;
    } catch (_error) {
      return false;
    }
  };

  const findVisibleTextTarget = (targetText) => {
    const selectors = "button, [role='tab'], [role='menuitem'], [role='button'], a, label, div, span";
    return Array.from(document.querySelectorAll(selectors)).find((el) => {
      if (!isVisible(el)) return false;
      const text = (el.textContent || "").trim();
      return textLike(text, targetText) || textIncludes(text, targetText);
    }) || null;
  };

  const getVisibleComboboxes = () => Array.from(document.querySelectorAll('[role="combobox"]')).filter(isVisible);

  const getVisibleTextareas = () => Array.from(document.querySelectorAll("textarea")).filter(isVisible);

  const findVideoFrameZone = (label) => {
    const oppositeLabel = label === "首帧" ? "尾帧" : label === "尾帧" ? "首帧" : "";
    const candidates = Array.from(document.querySelectorAll("[class*='reference-item'], [class*='reference-upload-'], [data-testid*='upload'], [class*='upload']"));
    const scoredCandidates = candidates.map((candidate, index) => {
      const ownText = (candidate.textContent || "").replace(/\s+/g, " ").trim();
      const parentText = (candidate.parentElement?.textContent || "").replace(/\s+/g, " ").trim();
      const closestText = (candidate.closest("[class*='reference-item']")?.textContent || "").replace(/\s+/g, " ").trim();
      let score = 0;
      if (isVisible(candidate)) score += 100;
      if (textIncludes(ownText, label)) score += 400;
      if (textIncludes(closestText, label)) score += 250;
      if (textIncludes(parentText, label)) score += 120;
      if (candidate.querySelector("input[type='file']")) score += 80;
      if (oppositeLabel && textIncludes(ownText, oppositeLabel)) score -= 220;
      if (oppositeLabel && textIncludes(closestText, oppositeLabel)) score -= 120;
      score -= Math.min(ownText.length, 400) / 20;
      return { candidate, index, score };
    }).filter((entry) => entry.score > 0).sort((a, b) => b.score - a.score || a.index - b.index);

    if (scoredCandidates[0]) {
      return scoredCandidates[0].candidate;
    }

    for (const el of document.querySelectorAll("*")) {
      if (!isVisible(el)) continue;
      const text = el.textContent || "";
      if (!textIncludes(text, label)) continue;
      if (el.querySelector("input[type='file']")) return el;
      const parent = el.closest("[class*='reference-item'], [class*='reference-upload-'], [data-testid*='upload'], [class*='upload']");
      if (parent) return parent;
    }
    return null;
  };

  const getUploadRelatedText = (el) => {
    if (!el) return "";
    return [
      el.textContent || "",
      el.parentElement?.textContent || "",
      el.closest("[class*='reference-item'], [class*='reference-upload-'], [data-testid*='upload'], [class*='upload']")?.textContent || "",
    ].join(" ").replace(/\s+/g, " ").trim();
  };

  const findFileInputNearZone = (zone, label = "") => {
    if (!zone) return null;
    const parent = zone.closest("[class*='reference-item'], [class*='reference-upload-'], [data-testid*='upload'], [class*='upload']");
    const inputs = Array.from(document.querySelectorAll("input[type='file']"));
    const scored = inputs.map((input, index) => {
      const owner = input.closest("[class*='reference-item'], [class*='reference-upload-'], [data-testid*='upload'], [class*='upload']");
      const relatedText = getUploadRelatedText(owner || input);
      let score = 0;
      if (zone.contains(input)) score += 1000;
      if (owner && zone.contains(owner)) score += 900;
      if (owner && parent && owner === parent) score += 800;
      if (label && textIncludes(relatedText, label)) score += 500;
      if (owner && label && textIncludes(getUploadRelatedText(owner.parentElement), label)) score += 200;
      return { input, index, score };
    }).sort((a, b) => b.score - a.score || a.index - b.index);
    return scored[0]?.score > 0 ? scored[0].input : null;
  };

  const setElementText = (el, value) => {
    const nextValue = value || "";
    el.focus();
    if ("value" in el) {
      const proto = el.tagName === "TEXTAREA" ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
      if (setter) setter.call(el, nextValue);
      else el.value = nextValue;
      el.dispatchEvent(new InputEvent("input", { bubbles: true, data: nextValue }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return;
    }
    el.textContent = nextValue;
    el.dispatchEvent(new InputEvent("input", { bubbles: true, data: nextValue }));
  };

  const waitForJimengVideoReady = async (options = {}) => waitFor(() => {
    const signal = getVisibleTextareas()[0]
      || findVideoFrameZone("首帧")
      || getVisibleComboboxes()[0]
      || Array.from(document.querySelectorAll("button")).find((btn) => {
        if (!isVisible(btn)) return false;
        const text = btn.textContent || "";
        return textIncludes(text, "生成") || textIncludes(text, "Seedance") || /\d+:\d+/.test(text);
      });
    return signal || null;
  }, {
    timeoutMs: options.timeoutMs ?? 60000,
    intervalMs: options.intervalMs ?? 250,
    label: options.label || "jimeng_video_ready",
  });

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
        await waitFor(() => document.querySelector('[role="combobox"]'), { timeoutMs: 15000, label: "combobox" });
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
      const clicked = clickElement(findVisibleTextTarget("图片生成"));
      /*
        const els = document.querySelectorAll("*");
        for (const el of els) {
          if (el.childNodes.length === 1 && textLike(el.textContent, "图片生成")) {
            el.click(); return true;
          }
        }
        return false;
      */
      if (!clicked) return { ok: false, data: null, error: "图片生成 tab not found" };
      await delay(1000);
      // Wait for page to transition
      await waitFor(() => window.location.href.includes("type=image"), { timeoutMs: 15000, label: "type=image URL" });
      await waitFor(() => document.querySelector('[role="combobox"]'), { timeoutMs: 15000, label: "combobox" });
      return { ok: true, data: { status: "clicked_via_evaluate" }, error: null };
    }

    const parentClickable = tab.parentElement;
    const isMenuItem = parentClickable && (parentClickable.getAttribute("role")?.includes("menu") ||
      parentClickable.className?.includes("menu") || parentClickable.tagName === "LI");

    if (!isMenuItem && textLike(tab.textContent, "图片生成")) {
      const parentVisible = parentClickable && isVisible(parentClickable);
      if (parentVisible) {
        clickElement(parentClickable);
        await delay(1000);
        const secondClick = Array.from(document.querySelectorAll("*")).find(el =>
          textLike(el.textContent, "图片生成") && isVisible(el) && el !== tab
        );
        if (secondClick) { clickElement(secondClick); }
        // Wait for page transition
        await waitFor(() => window.location.href.includes("type=image"), { timeoutMs: 15000, label: "type=image URL" });
        return { ok: true, data: { status: "parent_then_option", parentTag: parentClickable.tagName }, error: null };
      }
      clickElement(tab);
      await delay(1000);
      const option = Array.from(document.querySelectorAll("*")).find(el =>
        textLike(el.textContent, "图片生成") && isVisible(el) && el !== tab
      );
      if (option) { clickElement(option); }
      await waitFor(() => window.location.href.includes("type=image"), { timeoutMs: 15000, label: "type=image URL" });
      return { ok: true, data: { status: "trigger_then_option" }, error: null };
    }

    clickElement(tab);
    await waitFor(() => window.location.href.includes("type=image"), { timeoutMs: 15000, label: "type=image URL" });
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
      await waitFor(() => document.querySelector('[role="combobox"]'), { timeoutMs: 20000, label: "model_combobox" });
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
    const targetBtn = await waitFor(() => {
      const btn = document.querySelector('button[class*="submit-button"]:not([disabled])');
      return btn || null;
    }, { timeoutMs: 300000, label: "enabled_submit_button" });

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
    let firstWaitDone = false;

    while (Date.now() < deadline && resultUrls.length < 4) {
      const thumbnails = getThumbnailImages();

      if (thumbnails.length === 0) {
        if (!firstWaitDone) {
          console.log("[stepWait] no thumbnails yet, waiting 80s for first generation...");
          await delay(80000);
          firstWaitDone = true;
          tryIndex = 0;
          continue;
        } else {
          console.log("[stepWait] no thumbnails, retrying in 10s...");
          await delay(10000);
          tryIndex = 0;
          continue;
        }
      }

      console.log("[stepWait] thumbnails:", thumbnails.length, "captured:", resultUrls.length, "next index:", tryIndex);

      // Try the next uncaptured thumbnail
      if (tryIndex >= thumbnails.length) {
        console.log("[stepWait] all thumbnails tried, waiting 10s before retry...");
        tryIndex = 0;
        await delay(10000);
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
        await delay(10000);
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
  const VIDEO_HARDCODE_URL = "https://jimeng.jianying.com/ai-tool/home/?type=video&workspace=undefined";

  async function stepVideoNav(targetUrl) {
    const target = VIDEO_HARDCODE_URL;
    if (window.location.href !== target) {
      window.location.href = target;
      // Wait for exact URL match — ensures page has fully loaded before returning
      await waitFor(() => window.location.href === target, { timeoutMs: 60000, label: "video_page_navigated" });
    }
    // Wait for page DOM to be ready (comboboxes appear)
    await waitFor(() => document.querySelector('[role="combobox"]'), { timeoutMs: 60000, label: "page_ready" });
    return { ok: true, data: { status: "navigated", url: window.location.href }, error: null };
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
    const targetOption = options.find(el => textIncludes(el.textContent || "", "Seedance 1.0 Fast"));
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
  // Hardened video step overrides
  // ---------------------------------------------------------------------------

  const DEFAULT_JIMENG_VIDEO_URL = "https://jimeng.jianying.com/ai-tool/home/?type=video&workspace=0";

  const normalizeJimengVideoUrl = (targetUrl) => {
    try {
      const url = new URL(targetUrl || DEFAULT_JIMENG_VIDEO_URL);
      url.searchParams.set("type", "video");
      if (!url.searchParams.get("workspace") || url.searchParams.get("workspace") === "undefined") {
        url.searchParams.set("workspace", "0");
      }
      return url.toString();
    } catch (_error) {
      return DEFAULT_JIMENG_VIDEO_URL;
    }
  };

  const getVideoOptionText = (el) => {
    const directText = (el.textContent || "").trim();
    if (directText) return directText;
    return (el.getAttribute("aria-label") || "").trim();
  };

  const assignFileToInput = (fileInput, file) => {
    const transfer = new DataTransfer();
    transfer.items.add(file);
    fileInput.files = transfer.files;
    fileInput.dispatchEvent(new Event("input", { bubbles: true }));
    fileInput.dispatchEvent(new Event("change", { bubbles: true }));
  };

  async function stepVideoNav(targetUrl) {
    const target = normalizeJimengVideoUrl(targetUrl);
    const shouldNavigate = !window.location.href.includes("type=video")
      || window.location.search.includes("workspace=undefined");

    if (shouldNavigate) {
      window.location.href = target;
    }

    await waitFor(() => window.location.href.includes("type=video"), {
      timeoutMs: 60000,
      label: "video_page_navigated",
    });
    await waitForJimengVideoReady({ timeoutMs: 60000, label: "video_page_ready" });
    return { ok: true, data: { status: shouldNavigate ? "navigated" : "already_on_page", url: window.location.href }, error: null };
  }

  async function stepVideoTab() {
    if (window.location.href.includes("type=video")) {
      try {
        await waitForJimengVideoReady({ timeoutMs: 20000, label: "video_tab_ready" });
        return { ok: true, data: { status: "already_on_video_tab" }, error: null };
      } catch {
        return { ok: false, data: null, error: "type=video page loaded but page controls never became ready" };
      }
    }

    const tab = findVisibleTextTarget("视频生成");
    if (!tab) return { ok: false, data: null, error: "视频生成 tab not found" };

    clickElement(tab.parentElement && isVisible(tab.parentElement) ? tab.parentElement : tab);
    await delay(1000);

    const option = findVisibleTextTarget("视频生成");
    if (option && option !== tab) clickElement(option);

    await waitFor(() => window.location.href.includes("type=video"), {
      timeoutMs: 30000,
      label: "type=video URL",
    });
    await waitForJimengVideoReady({ timeoutMs: 20000, label: "video_tab_ready_after_click" });
    return { ok: true, data: { status: "clicked_video_tab" }, error: null };
  }

  async function stepVideoModel() {
    await waitForJimengVideoReady({ timeoutMs: 30000, label: "video_model_ready" });

    const comboboxes = getVisibleComboboxes();
    const modelCombobox = comboboxes.find((el) => textIncludes(el.textContent || "", "Seedance"))
      || comboboxes.find((el) => {
        const text = el.textContent || "";
        return !/\d+:\d+/.test(text) && !textIncludes(text, "秒");
      })
      || comboboxes[0];

    if (!modelCombobox) {
      throw new Error("Video model combobox not found");
    }

    clickElement(modelCombobox);
    await delay(500);

    const listbox = await waitFor(() => {
      return Array.from(document.querySelectorAll('[role="listbox"]')).find(isVisible) || null;
    }, { timeoutMs: 5000, label: "video_model_listbox" }).catch(() => null);

    if (listbox) {
      const options = Array.from(listbox.querySelectorAll('[role="option"], li, button, div')).filter((el) => {
        const text = getVideoOptionText(el);
        return !!text;
      });

      const targetOption = options.find((el) => {
        const text = getVideoOptionText(el);
        return textIncludes(text, "Seedance 1.0 Fast");
      });

      if (targetOption) {
        clickElement(targetOption);
        await delay(500);
      } else {
        document.body.click();
        await delay(200);
      }
    } else {
      document.body.click();
      await delay(200);
    }

    if (!findVideoFrameZone("尾帧")) {
      const frameModeTarget = findVisibleTextTarget("首尾帧");
      if (frameModeTarget) {
        clickElement(frameModeTarget);
        await delay(800);
      }
    }

    await waitFor(() => findVideoFrameZone("首帧") || getVisibleTextareas()[0] || null, {
      timeoutMs: 15000,
      label: "video_mode_controls",
    });

    return {
      ok: true,
      data: {
        modelText: (modelCombobox.textContent || "").trim(),
        hasLastFrameZone: !!findVideoFrameZone("尾帧"),
      },
      error: null,
    };
  }

  async function stepVideoRatio(job) {
    const ratio = job.aspectRatio || "16:9";
    if (ratio === "16:9") {
      return { ok: true, data: { ratio: "16:9", status: "default_ratio" }, error: null };
    }

    const ratioBtn = Array.from(document.querySelectorAll("button")).filter(isVisible).find((el) => /\d+:\d+/.test(el.textContent || ""));
    if (!ratioBtn) {
      const allBtns = Array.from(document.querySelectorAll("button")).filter(isVisible).map((el) => (el.textContent || "").trim().slice(0, 40)).join(" | ");
      throw new Error(`Ratio button not found (buttons: ${allBtns})`);
    }

    clickElement(ratioBtn);
    await delay(400);

    const ratioLabel = Array.from(document.querySelectorAll("label.lv-radio, [role='radio'], button, div")).find((el) => {
      return isVisible(el) && textLike((el.textContent || "").trim(), ratio);
    });
    if (!ratioLabel) {
      const allLabels = Array.from(document.querySelectorAll("label.lv-radio, [role='radio']")).map((el) => (el.textContent || "").trim()).join(" | ");
      throw new Error(`Ratio ${ratio} not found in dropdown (found: ${allLabels})`);
    }

    clickElement(ratioLabel);
    await delay(200);
    document.body.click();
    await delay(200);
    return { ok: true, data: { ratio }, error: null };
  }

  async function stepVideoUploadFirstFrame(asset) {
    if (!asset) return { ok: false, data: null, error: "first frame asset is required" };

    const zone = findVideoFrameZone("首帧");
    if (!zone) return { ok: false, data: null, error: "first frame upload zone not found" };

    const fileInput = findFileInputNearZone(zone);
    if (!fileInput) return { ok: false, data: null, error: "first frame file input not found" };

    const response = await bridgeFetch({ url: asset.url, responseType: "blobBase64" });
    const binary = atob(response.base64Data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const mimeType = asset.mimeType || response.mimeType || "application/octet-stream";
    const file = new File([bytes], asset.name, { type: mimeType });
    assignFileToInput(fileInput, file);

    await waitFor(() => {
      const imgs = zone.querySelectorAll("img");
      return Array.from(imgs).find((img) => {
        try {
          return img.getBoundingClientRect().width > 50
            && !img.src.startsWith("data:")
            && !img.src.startsWith("blob:");
        } catch {
          return false;
        }
      }) || null;
    }, { timeoutMs: 20000, label: "first_frame_preview" });

    return { ok: true, data: { status: "uploaded", name: asset.name }, error: null };
  }

  async function stepVideoUploadLastFrame(asset) {
    if (!asset) return { ok: true, data: { status: "skipped", reason: "no_asset" }, error: null };

    const zone = findVideoFrameZone("尾帧");
    if (!zone) return { ok: false, data: null, error: "last frame upload zone not found" };

    const fileInput = findFileInputNearZone(zone);
    if (!fileInput) return { ok: false, data: null, error: "last frame file input not found" };

    const response = await bridgeFetch({ url: asset.url, responseType: "blobBase64" });
    const binary = atob(response.base64Data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const mimeType = asset.mimeType || response.mimeType || "application/octet-stream";
    const file = new File([bytes], asset.name, { type: mimeType });
    assignFileToInput(fileInput, file);

    await waitFor(() => {
      const imgs = zone.querySelectorAll("img");
      return Array.from(imgs).find((img) => {
        try {
          return img.getBoundingClientRect().width > 50
            && !img.src.startsWith("data:")
            && !img.src.startsWith("blob:");
        } catch {
          return false;
        }
      }) || null;
    }, { timeoutMs: 20000, label: "last_frame_preview" });

    return { ok: true, data: { status: "uploaded", name: asset.name }, error: null };
  }

  async function stepVideoPrompt(job) {
    await waitForJimengVideoReady({ timeoutMs: 30000, label: "video_prompt_ready" });

    const textareas = getVisibleTextareas();
    if (textareas.length === 0) {
      return { ok: false, data: null, error: "No textarea found for video prompt input" };
    }

    const movementText = job.movement || job.prompt || "";
    const promptText = job.prompt || "";

    const movementTextarea = textareas.find((el) => {
      const placeholder = el.getAttribute("placeholder") || "";
      return textIncludes(placeholder, "动作") || textIncludes(placeholder, "运动");
    }) || textareas[0];

    const promptTextarea = textareas.find((el) => {
      if (el === movementTextarea) return false;
      const placeholder = el.getAttribute("placeholder") || "";
      return textIncludes(placeholder, "描述") || textIncludes(placeholder, "创意");
    }) || textareas.find((el) => el !== movementTextarea) || movementTextarea;

    setElementText(movementTextarea, movementText);
    await delay(200);

    if (promptTextarea && promptTextarea !== movementTextarea) {
      setElementText(promptTextarea, promptText);
      await delay(200);
    } else if (promptText && promptTextarea === movementTextarea) {
      setElementText(promptTextarea, `${movementText}\n${promptText}`.trim());
      await delay(200);
    }

    return { ok: true, data: { promptLength: promptText.length, movementLength: movementText.length }, error: null };
  }

  let _videoGenerateClicked = false;

  async function stepVideoGenerate() {
    if (_videoGenerateClicked) {
      return { ok: true, data: { skipped: true }, error: null };
    }
    _videoGenerateClicked = true;
    try {
      const pickGenerateButton = () => {
        const buttons = Array.from(document.querySelectorAll("button")).filter((btn) => isVisible(btn) && !btn.disabled);
        const scored = buttons.map((btn) => {
          const text = (btn.textContent || "").trim();
          let score = 0;
          if (textIncludes(text, "生成")) score += 5;
          if ((btn.className || "").includes("primary")) score += 3;
          if ((btn.className || "").includes("lv-btn-primary")) score += 2;
          if (textIncludes(text, "查看") || textIncludes(text, "上传")) score -= 4;
          return { btn, score };
        }).filter((entry) => entry.score > 0).sort((a, b) => b.score - a.score);
        return scored[0]?.btn || null;
      };

      const targetBtn = await waitFor(() => pickGenerateButton(), {
        timeoutMs: 300000,
        label: "video_generate_button",
      });

      if (!targetBtn) {
        const allBtns = Array.from(document.querySelectorAll("button")).slice(0, 8).map((b) =>
          `dis:${b.disabled} cls:${String(b.className).slice(0, 35)} txt:${(b.textContent || "").trim().slice(0, 12)}`
        ).join(" | ");
        throw new Error(`Generate button never became enabled (all_btns: ${allBtns})`);
      }

      clickElement(targetBtn);
      await delay(300);

      const processing = await waitFor(() => {
        if (window.location.href.includes("/generate")) return true;
        if (targetBtn.disabled) return true;
        return Array.from(document.querySelectorAll("button")).some((btn) => {
          if (!isVisible(btn)) return false;
          const text = btn.textContent || "";
          return btn.disabled && textIncludes(text, "生成");
        }) || null;
      }, { timeoutMs: 15000, label: "video_generate_submission" }).catch(() => null);

      return {
        ok: true,
        data: {
          clicked: (targetBtn.textContent || "").trim().slice(0, 30),
          processing: !!processing,
        },
        error: null,
      };
    } finally {
      _videoGenerateClicked = false;
    }
  }

  async function stepVideoWait(job) {
    const TIMEOUT_MS = (job.timeoutSeconds ? job.timeoutSeconds : 600) * 1000;
    const deadline = Date.now() + TIMEOUT_MS;
    const POLL_INTERVAL_MS = 3000;
    const STABLE_THRESHOLD_MS = 8000;
    let lastCandidateKey = "";
    let stableSince = 0;
    let lastViewClickAt = 0;

    const collectVideoCandidates = () => {
      const candidates = [];
      const pushCandidate = (url, sourceType) => {
        const value = String(url || "").trim();
        if (!value || value.startsWith("data:") || value.startsWith("blob:")) return;
        candidates.push({ videoUrl: value, sourceType });
      };

      for (const videoEl of document.querySelectorAll("video")) {
        pushCandidate(videoEl.currentSrc || videoEl.src, "videoElement");
      }
      for (const sourceEl of document.querySelectorAll("video source[src]")) {
        pushCandidate(sourceEl.src, "videoSource");
      }
      for (const linkEl of document.querySelectorAll("a[href]")) {
        const href = linkEl.href || "";
        if (/\.(mp4|webm)(\?|$)/i.test(href) || /video/i.test(href)) {
          pushCandidate(href, "downloadLink");
        }
      }

      const deduped = [];
      const seen = new Set();
      for (const candidate of candidates) {
        const key = `${candidate.sourceType}:${candidate.videoUrl}`;
        if (seen.has(key)) continue;
        seen.add(key);
        deduped.push(candidate);
      }
      return deduped;
    };

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

    while (Date.now() < deadline) {
      const candidates = collectVideoCandidates();
      const current = candidates[0];

      if (current) {
        const key = `${current.sourceType}:${current.videoUrl}`;
        if (key !== lastCandidateKey) {
          lastCandidateKey = key;
          stableSince = Date.now();
          console.log("[stepVideoWait] candidate changed:", current.sourceType, current.videoUrl.slice(0, 80));
        } else if (Date.now() - stableSince >= STABLE_THRESHOLD_MS) {
          return { ok: true, data: current, error: null };
        }
      }

      const now = Date.now();
      if (now - lastViewClickAt >= 10000) {
        const viewBtn = Array.from(document.querySelectorAll("a, button")).find((el) => {
          if (!isVisible(el)) return false;
          const text = el.textContent || "";
          return textIncludes(text, "去查看") || textIncludes(text, "查看结果");
        });
        if (viewBtn) {
          clickElement(viewBtn);
          lastViewClickAt = now;
          await delay(1500);
          continue;
        }
      }

      await delay(POLL_INTERVAL_MS);
    }

    return { ok: false, data: null, error: `Timed out after ${job.timeoutSeconds || 600}s, no video found` };
  }

  async function stepVideoModel() {
    await waitForJimengVideoReady({ timeoutMs: 30000, label: "video_model_ready" });

    const getControlText = (el) => getVideoOptionText(el).replace(/\s+/g, " ").trim();
    const isDurationText = (text) => /^\d+\s*s$/i.test(text) || textIncludes(text, "秒");
    const isRatioText = (text) => /\d+:\d+/.test(text);
    const isFrameModeText = (text) => textIncludes(text, "首尾帧") || textIncludes(text, "首帧") || textIncludes(text, "尾帧");
    const isTabText = (text) => textIncludes(text, "视频生成") || textIncludes(text, "图片生成");
    const looksLikeModelText = (text) => {
      if (!text) return false;
      if (textIncludes(text, "Seedance")) return true;
      if (isRatioText(text) || isDurationText(text) || isFrameModeText(text) || isTabText(text)) return false;
      return /\d+\.\d+/.test(text);
    };

    const comboboxes = getVisibleComboboxes();
    const fallbackControls = Array.from(document.querySelectorAll(
      '[role="combobox"], button, [role="button"], [aria-haspopup="listbox"], [aria-expanded]'
    )).filter(isVisible);
    const dedupedControls = Array.from(new Set([...comboboxes, ...fallbackControls]));
    const visibleControlTexts = dedupedControls
      .map((el) => getControlText(el))
      .filter(Boolean)
      .slice(0, 12)
      .join(" | ");

    const modelControl = dedupedControls.find((el) => textIncludes(getControlText(el), "Seedance"))
      || dedupedControls.find((el) => looksLikeModelText(getControlText(el)));

    if (!modelControl) {
      const frameReady = findVideoFrameZone("首帧") || findVideoFrameZone("尾帧");
      if (frameReady) {
        return {
          ok: true,
          data: {
            status: "model_control_missing_but_frame_controls_ready",
            modelText: "",
            hasLastFrameZone: !!findVideoFrameZone("尾帧"),
          },
          error: null,
        };
      }
      throw new Error(`Video model control not found (visible controls: ${visibleControlTexts || "none"})`);
    }

    clickElement(modelControl);
    await delay(500);

    const listbox = await waitFor(() => {
      return Array.from(document.querySelectorAll('[role="listbox"]')).find(isVisible) || null;
    }, { timeoutMs: 5000, label: "video_model_listbox" }).catch(() => null);

    if (listbox) {
      const options = Array.from(listbox.querySelectorAll('[role="option"], li, button, div')).filter((el) => {
        const text = getVideoOptionText(el);
        return !!text;
      });

      const targetOption = options.find((el) => {
        const text = getVideoOptionText(el);
        return textIncludes(text, "Seedance 1.0 Fast");
      });

      if (targetOption) {
        clickElement(targetOption);
        await delay(500);
      } else {
        document.body.click();
        await delay(200);
      }
    } else {
      document.body.click();
      await delay(200);
    }

    if (!findVideoFrameZone("尾帧")) {
      const frameModeTarget = findVisibleTextTarget("首尾帧");
      if (frameModeTarget) {
        clickElement(frameModeTarget);
        await delay(800);
      }
    }

    await waitFor(() => findVideoFrameZone("首帧") || getVisibleTextareas()[0] || null, {
      timeoutMs: 15000,
      label: "video_mode_controls",
    });

    return {
      ok: true,
      data: {
        modelText: getControlText(modelControl),
        hasLastFrameZone: !!findVideoFrameZone("尾帧"),
      },
      error: null,
    };
  }

  const getFrameZoneState = (zone, fileInput) => {
    const imgs = Array.from(zone.querySelectorAll("img")).filter((img) => {
      try {
        return img.getBoundingClientRect().width > 24 && img.getBoundingClientRect().height > 24;
      } catch {
        return false;
      }
    });
    const canvases = Array.from(zone.querySelectorAll("canvas")).filter((canvas) => {
      try {
        return canvas.getBoundingClientRect().width > 24 && canvas.getBoundingClientRect().height > 24;
      } catch {
        return false;
      }
    });
    const videos = Array.from(zone.querySelectorAll("video")).filter((video) => {
      try {
        return video.getBoundingClientRect().width > 24 && video.getBoundingClientRect().height > 24;
      } catch {
        return false;
      }
    });
    const text = (zone.textContent || "").replace(/\s+/g, " ").trim();
    const buttonTexts = Array.from(zone.querySelectorAll("button, [role='button']")).filter(isVisible).map((el) => {
      return (el.textContent || el.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim();
    }).filter(Boolean);
    const fileCount = fileInput?.files?.length || 0;
    const fileNames = Array.from(fileInput?.files || []).map((file) => file.name);
    const hasReadyText = ["重传", "重新上传", "替换", "删除", "移除", "自动匹配"].some((label) => textIncludes(text, label));
    const hasReadyButton = ["自动匹配", "替换", "重传", "删除"].some((label) => buttonTexts.some((textValue) => textIncludes(textValue, label)));
    const imgKinds = imgs.map((img) => {
      const src = img.currentSrc || img.src || "";
      if (src.startsWith("blob:")) return "blob";
      if (src.startsWith("data:")) return "data";
      if (src.startsWith("http")) return "http";
      return src ? "other" : "empty";
    });
    return {
      previewCount: imgs.length,
      canvasCount: canvases.length,
      videoCount: videos.length,
      fileCount,
      fileNames,
      hasReadyText,
      hasReadyButton,
      buttonTexts: buttonTexts.slice(0, 6),
      textSample: text.slice(0, 120),
      imgKinds,
    };
  };

  const getGlobalVideoUploadState = () => {
    const actionTexts = Array.from(document.querySelectorAll("button, [role='button'], a")).filter(isVisible).map((el) => {
      return (el.textContent || el.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim();
    }).filter(Boolean);
    const matchedActionTexts = actionTexts.filter((text) => {
      return ["自动匹配", "替换", "重传", "重新上传", "删除", "移除"].some((label) => textIncludes(text, label));
    });
    const fileNames = Array.from(document.querySelectorAll("input[type='file']")).flatMap((input) => {
      return Array.from(input.files || []).map((file) => file.name);
    });
    return {
      matchedActionTexts: matchedActionTexts.slice(0, 10),
      fileNames: fileNames.slice(0, 10),
      signature: `${matchedActionTexts.join("|")}::${fileNames.join("|")}`,
    };
  };

  const getUploadStabilitySignature = (zone, fileInput) => {
    const localState = getFrameZoneState(zone, fileInput);
    const globalState = getGlobalVideoUploadState();
    return JSON.stringify({
      previewCount: localState.previewCount,
      canvasCount: localState.canvasCount,
      videoCount: localState.videoCount,
      fileCount: localState.fileCount,
      fileNames: localState.fileNames,
      hasReadyText: localState.hasReadyText,
      hasReadyButton: localState.hasReadyButton,
      buttonTexts: localState.buttonTexts,
      imgKinds: localState.imgKinds,
      globalMatchedActionTexts: globalState.matchedActionTexts,
      globalFileNames: globalState.fileNames,
    });
  };

  async function stepVideoUploadFrame(asset, zoneLabel, waitLabel) {
    if (!asset) {
      return { ok: false, data: null, error: `${zoneLabel} asset is required` };
    }

    const locateUploadTarget = () => {
      const currentZone = findVideoFrameZone(zoneLabel);
      if (!currentZone) return null;
      const currentInput = findFileInputNearZone(currentZone, zoneLabel);
      if (!currentInput) return null;
      return { zone: currentZone, fileInput: currentInput };
    };

    const evaluateUploadedState = (state, previousState) => {
      const localButtonsChanged = state.buttonTexts.join("|") !== previousState.buttonTexts.join("|");
      const localTextChanged = state.textSample !== previousState.textSample;
      const visualReady = state.previewCount > previousState.previewCount
        || state.canvasCount > previousState.canvasCount
        || state.videoCount > previousState.videoCount
        || state.hasReadyText
        || state.hasReadyButton
        || localButtonsChanged
        || localTextChanged
        || state.imgKinds.some((kind) => kind === "blob" || kind === "data" || kind === "http");
      const fileReady = state.fileCount > 0 && state.fileNames.includes(asset.name);
      return visualReady || fileReady;
    };

    const target = locateUploadTarget();
    if (!target) {
      return { ok: false, data: null, error: `${zoneLabel} upload zone not found` };
    }
    let { zone, fileInput } = target;
    clickElement(zone);
    await delay(200);

    const beforeState = getFrameZoneState(zone, fileInput);
    const beforeGlobalState = getGlobalVideoUploadState();
    const response = await bridgeFetch({ url: asset.url, responseType: "blobBase64" });
    const binary = atob(response.base64Data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const mimeType = asset.mimeType || response.mimeType || "application/octet-stream";
    const file = new File([bytes], asset.name, { type: mimeType });

    const tryUpload = async (currentZone, currentInput, previousState, previousGlobalState, timeoutMs) => {
      assignFileToInput(currentInput, file);
      await delay(300);
      clickElement(currentZone);
      return waitFor(() => {
        const refreshed = locateUploadTarget();
        const liveZone = refreshed?.zone || currentZone;
        const liveInput = refreshed?.fileInput || currentInput;
        const state = getFrameZoneState(liveZone, liveInput);
        const globalState = getGlobalVideoUploadState();
        const globalChanged = globalState.signature !== previousGlobalState.signature;
        const globalReady = globalState.fileNames.includes(asset.name)
          || (globalChanged && globalState.matchedActionTexts.length > 0);
        return (evaluateUploadedState(state, previousState) || globalReady)
          ? { ...state, globalMatchedActionTexts: globalState.matchedActionTexts }
          : null;
      }, { timeoutMs, label: waitLabel }).catch(() => null);
    };

    let uploadedState = await tryUpload(zone, fileInput, beforeState, beforeGlobalState, 25000);

    if (!uploadedState) {
      await delay(1200);
      const retryTarget = locateUploadTarget();
      if (retryTarget) {
        zone = retryTarget.zone;
        fileInput = retryTarget.fileInput;
        const retryBeforeState = getFrameZoneState(zone, fileInput);
        const retryBeforeGlobalState = getGlobalVideoUploadState();
        uploadedState = await tryUpload(zone, fileInput, retryBeforeState, retryBeforeGlobalState, 15000);
      }
    }

    if (!uploadedState) {
      const afterState = getFrameZoneState(zone, fileInput);
      return {
        ok: false,
        data: { beforeState, afterState },
        error: `${zoneLabel} upload did not produce a visible preview or retained file selection`,
      };
    }

    const STABLE_UPLOAD_MS = 1800;
    let stableSignature = "";
    let stableSince = 0;
    await waitFor(() => {
      const refreshed = locateUploadTarget();
      const liveZone = refreshed?.zone || zone;
      const liveInput = refreshed?.fileInput || fileInput;
      const signature = getUploadStabilitySignature(liveZone, liveInput);
      if (signature !== stableSignature) {
        stableSignature = signature;
        stableSince = Date.now();
        return null;
      }
      return Date.now() - stableSince >= STABLE_UPLOAD_MS ? true : null;
    }, { timeoutMs: 5000, label: `${waitLabel}_stable` }).catch(() => null);

    await delay(400);

    return {
      ok: true,
      data: {
        status: "uploaded",
        name: asset.name,
        previewCount: uploadedState.previewCount,
        fileCount: uploadedState.fileCount,
        imgKinds: uploadedState.imgKinds,
        globalMatchedActionTexts: uploadedState.globalMatchedActionTexts || [],
      },
      error: null,
    };
  }

  async function stepVideoUploadFirstFrame(asset) {
    return stepVideoUploadFrame(asset, "首帧", "first_frame_preview");
  }

  async function stepVideoUploadLastFrame(asset) {
    if (!asset) {
      return { ok: true, data: { status: "skipped", reason: "no_asset" }, error: null };
    }
    return stepVideoUploadFrame(asset, "尾帧", "last_frame_preview");
  }

  async function stepVideoWait(job) {
    const TIMEOUT_MS = (job.timeoutSeconds ? job.timeoutSeconds : 600) * 1000;
    const deadline = Date.now() + TIMEOUT_MS;
    const POLL_INTERVAL_MS = 3000;
    const STABLE_THRESHOLD_MS = 8000;
    let lastCandidateKey = "";
    let stableSince = 0;
    let lastViewClickAt = 0;
    let enteredResult = false;

    const getResultActionText = (el) => (el.textContent || el.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim();
    const findResultAction = () => {
      const actions = Array.from(document.querySelectorAll("a, button, [role='button']")).filter(isVisible);
      return actions.find((el) => {
        const text = getResultActionText(el);
        return textIncludes(text, "去查看") || textIncludes(text, "查看结果") || textIncludes(text, "立即查看");
      }) || null;
    };

    const findDirectResultTrigger = () => {
      const videoEl = Array.from(document.querySelectorAll("video")).find(isVisible);
      if (videoEl) {
        return videoEl.closest("a, button, [role='button']") || videoEl;
      }
      const videoLink = Array.from(document.querySelectorAll("a[href]")).find((el) => {
        if (!isVisible(el)) return false;
        const href = el.href || "";
        return /\.(mp4|webm)(\?|$)/i.test(href) || /video/i.test(href);
      });
      return videoLink || null;
    };

    const hasPendingGenerationText = () => {
      const pendingTexts = ["生成中", "排队中", "处理中", "预计", "等待中"];
      const candidates = Array.from(document.querySelectorAll("div, span, p, button")).filter(isVisible);
      return candidates.some((el) => {
        const text = (el.textContent || "").replace(/\s+/g, " ").trim();
        return pendingTexts.some((label) => textIncludes(text, label));
      });
    };

    const collectVideoCandidates = () => {
      const candidates = [];
      const pushCandidate = (url, sourceType, el) => {
        const value = String(url || "").trim();
        if (!value || value.startsWith("data:") || value.startsWith("blob:")) return;
        if (el && !isVisible(el)) return;
        candidates.push({ videoUrl: value, sourceType });
      };

      for (const videoEl of document.querySelectorAll("video")) {
        pushCandidate(videoEl.currentSrc || videoEl.src, "videoElement", videoEl);
      }
      for (const sourceEl of document.querySelectorAll("video source[src]")) {
        pushCandidate(sourceEl.src, "videoSource", sourceEl.closest("video"));
      }
      for (const linkEl of document.querySelectorAll("a[href]")) {
        const href = linkEl.href || "";
        if (/\.(mp4|webm)(\?|$)/i.test(href) || /video/i.test(href)) {
          pushCandidate(href, "downloadLink", linkEl);
        }
      }

      const deduped = [];
      const seen = new Set();
      for (const candidate of candidates) {
        const key = `${candidate.sourceType}:${candidate.videoUrl}`;
        if (seen.has(key)) continue;
        seen.add(key);
        deduped.push(candidate);
      }
      return deduped;
    };

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

    while (Date.now() < deadline) {
      const now = Date.now();
      const resultAction = findResultAction();
      const candidates = collectVideoCandidates();
      const current = candidates[0];
      const pending = hasPendingGenerationText();

      if (!enteredResult && resultAction && now - lastViewClickAt >= 5000) {
        clickElement(resultAction);
        enteredResult = true;
        lastViewClickAt = now;
        lastCandidateKey = "";
        stableSince = 0;
        console.log("[stepVideoWait] clicked result action:", getResultActionText(resultAction));
        await delay(2000);
        continue;
      }

      if (!enteredResult && !resultAction && current && !pending) {
        const directTrigger = findDirectResultTrigger();
        if (directTrigger && now - lastViewClickAt >= 5000) {
          clickElement(directTrigger);
          lastViewClickAt = now;
          console.log("[stepVideoWait] clicked direct result trigger");
          await delay(1500);
          if (collectVideoCandidates().length > 0) {
            enteredResult = true;
          }
          continue;
        }
        enteredResult = true;
        lastCandidateKey = "";
        stableSince = 0;
        console.log("[stepVideoWait] no result action; accepting direct video result state");
      }

      if (!enteredResult) {
        await delay(POLL_INTERVAL_MS);
        continue;
      }

      if (current) {
        const key = `${current.sourceType}:${current.videoUrl}`;
        if (key !== lastCandidateKey) {
          lastCandidateKey = key;
          stableSince = Date.now();
          console.log("[stepVideoWait] candidate changed:", current.sourceType, current.videoUrl.slice(0, 80));
        } else if (Date.now() - stableSince >= STABLE_THRESHOLD_MS && !pending) {
          return { ok: true, data: current, error: null };
        }
      }

      if (resultAction && now - lastViewClickAt >= 15000) {
        clickElement(resultAction);
        lastViewClickAt = now;
        await delay(1500);
        continue;
      }

      await delay(POLL_INTERVAL_MS);
    }

    return { ok: false, data: null, error: `Timed out after ${job.timeoutSeconds || 600}s, no real video found` };
  }

  async function stepVideoCheckFirstFrameUploaded(asset) {
    const zone = findVideoFrameZone("棣栧抚");
    if (!zone) {
      return { ok: false, data: null, error: "first frame upload zone not found" };
    }

    const fileInput = findFileInputNearZone(zone, "棣栧抚");
    if (!fileInput) {
      return { ok: false, data: null, error: "first frame file input not found" };
    }

    const state = getFrameZoneState(zone, fileInput);
    const globalState = getGlobalVideoUploadState();
    const expectedFileName = asset?.name || "";
    const uploaded = state.previewCount > 0
      || state.canvasCount > 0
      || state.videoCount > 0
      || state.hasReadyText
      || state.hasReadyButton
      || state.imgKinds.some((kind) => kind === "blob" || kind === "data" || kind === "http")
      || (expectedFileName && state.fileNames.includes(expectedFileName))
      || (expectedFileName && globalState.fileNames.includes(expectedFileName))
      || globalState.matchedActionTexts.length > 0;

    return {
      ok: uploaded,
      data: {
        previewCount: state.previewCount,
        fileCount: state.fileCount,
        fileNames: state.fileNames,
        imgKinds: state.imgKinds,
        globalMatchedActionTexts: globalState.matchedActionTexts,
      },
      error: uploaded ? null : "first frame upload not verified",
    };
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
  window.stepVideoCheckFirstFrameUploaded = stepVideoCheckFirstFrameUploaded;
  window.stepVideoPrompt = stepVideoPrompt;
  window.stepVideoGenerate = stepVideoGenerate;
  window.stepVideoWait = stepVideoWait;
})();
