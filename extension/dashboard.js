/* ── Dashboard Controller ──────────────────────────────────────
   Dashboard (dashboard.html) is the presentation layer.
   All business logic (job claiming, platform start/stop, polling)
   lives in background.js. This script sends messages to background
   and renders the state it receives back.
   ────────────────────────────────────────────────────────────── */

const PLATFORMS = [
  { id: "gpt-image",    name: "ChatGPT 图片",  abbr: "GPT-IMG" },
  { id: "jimeng-image", name: "即梦图片",      abbr: "JM-IMG"  },
  { id: "jimeng-video", name: "即梦视频",      abbr: "JM-VID"  },
];

/* ── State ─────────────────────────────────────────────────── */
const state = {
  serverUrl: "http://127.0.0.1:8765",
  confirmBeforeVideoGenerate: false,
  selectedPlatform: "",
  platforms: {},   // keyed by platform id (matches PLATFORMS ids)
  bridgeJobs: [],   // raw jobs from /v1/state
  activity: [],
};

/* ── Utility ───────────────────────────────────────────────── */
const esc = s => String(s)
  .replace(/&/g, "&amp;")
  .replace(/</g, "&lt;")
  .replace(/>/g, "&gt;");

function formatAge(iso) {
  if (!iso) return "—";
  const d = (Date.now() - new Date(iso)) / 1000;
  if (d < 5)   return "刚刚";
  if (d < 60)  return Math.floor(d) + "秒前";
  if (d < 3600) return Math.floor(d/60) + "分钟前";
  return Math.floor(d/3600) + "小时前";
}

function logActivity(message, level = "info") {
  state.activity.unshift({ at: new Date().toISOString(), message, level });
  if (state.activity.length > 200) state.activity = state.activity.slice(0, 200);
}

/* ── Bridge to background.js ─────────────────────────────── */
let bgConnected = false;   // whether background.js is reachable

function bgSend(message, retries = 2) {
  return new Promise((resolve) => {
    if (typeof chrome === "undefined" || !chrome.runtime || typeof chrome.runtime.sendMessage !== "function") {
      console.warn("[dashboard] chrome.runtime not available - dashboard must be opened through the extension icon");
      resolve({ ok: false, error: "extension_unavailable" });
      return;
    }

    const attempt = (attemptNumber) => {
      chrome.runtime.sendMessage(message, (resp) => {
        if (chrome.runtime.lastError) {
          console.warn(`[dashboard] runtime error (attempt ${attemptNumber}):`, chrome.runtime.lastError.message);
          bgConnected = false;
          // Retry if retries remain and looks like a connection error
          if (attemptNumber < retries && chrome.runtime.lastError.message.includes("Could not establish")) {
            setTimeout(() => attempt(attemptNumber + 1), 150);
            return;
          }
          resolve({ ok: false, error: chrome.runtime.lastError.message });
        } else {
          bgConnected = true;
          resolve(resp || {});
        }
      });
    };

    attempt(1);
  });
}

/* ── Direct bridge API (for stats only) ─────────────────── */
async function bridgeState() {
  try {
    const res = await fetch(state.serverUrl + "/v1/state", {
      signal: AbortSignal.timeout(4000),
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

/* ── Sync state from background ────────────────────────────── */
function syncFromBackground(backgroundState) {
  if (!backgroundState) return;

  if (backgroundState.serverUrl) state.serverUrl = backgroundState.serverUrl;
  if (typeof backgroundState.confirmBeforeVideoGenerate === "boolean") {
    state.confirmBeforeVideoGenerate = backgroundState.confirmBeforeVideoGenerate;
  }

  if (backgroundState.platforms) {
    for (const pid of Object.keys(backgroundState.platforms)) {
      const ps = backgroundState.platforms[pid];
      // background.js uses `running` (bool), not `runningCount`
      // also preserve currentJobIds for display
      state.platforms[pid] = {
        runningCount:   ps.running   ? 1 : 0,   // bool → count
        busyCount:      ps.busyCount      || 0,
        pendingCount:   ps.pendingCount   || 0,
        lastMessage:    ps.lastMessage    || "空闲",
        currentJobIds:  Array.isArray(ps.currentJobIds) ? ps.currentJobIds : [],
        lastError:      ps.lastError      || null,
        intervalSeconds: ps.intervalSeconds || 5,
        concurrency:     ps.concurrency     || 1,
      };
    }
  }
}

function syncBridgeJobs(jobs) {
  if (!Array.isArray(jobs)) return;
  state.bridgeJobs = jobs;
}

/* ── Render ─────────────────────────────────────────────────── */
function render() {
  renderSummary();
  renderPlatforms();
  renderGlobalBadge();
  renderActivity();
  renderConfirmToggle();
  const ts = document.getElementById("last-updated");
  if (ts) ts.textContent = "更新于 " + formatAge(new Date().toISOString());
}

function renderSummary() {
  // Compute from bridge jobs (source of truth for counts)
  const jobs = state.bridgeJobs || [];
  const completed = jobs.filter(j => j.status === "completed").length;
  const failed    = jobs.filter(j => j.status === "failed").length;
  const pending   = jobs.filter(j => j.status === "pending").length;
  const running   = jobs.filter(j => j.status === "claimed").length;

  let platformRunning = 0;
  for (const pid of Object.keys(state.platforms)) {
    if ((state.platforms[pid] || {}).runningCount > 0) platformRunning++;
  }

  const container = document.getElementById("summary-grid");
  if (!container) return;

  container.innerHTML = `
    <div class="summary-stat">
      <div class="summary-stat-label">已完成</div>
      <div class="summary-stat-value">${completed}</div>
    </div>
    <div class="summary-stat">
      <div class="summary-stat-label">失败</div>
      <div class="summary-stat-value ${failed > 0 ? 'danger' : ''}">${failed}</div>
    </div>
    <div class="summary-stat">
      <div class="summary-stat-label">排队中</div>
      <div class="summary-stat-value ${pending > 0 ? 'warn' : ''}">${pending}</div>
    </div>
    <div class="summary-stat">
      <div class="summary-stat-label">运行中</div>
      <div class="summary-stat-value">${running}</div>
    </div>
  `;

  const foot = document.getElementById("summary-foot");
  if (foot) {
    const total = jobs.length;
    foot.textContent = total === 0
      ? "队列暂无任务，点击启动开始。"
      : `共 ${total} 个任务 · ${running} 个运行中`;
  }
}

function renderGlobalBadge() {
  const anyRunning = Object.values(state.platforms).some(s => s.runningCount > 0);
  const badge = document.getElementById("global-badge");
  if (badge) {
    badge.style.display = anyRunning ? "" : "none";
  }
}

function renderPlatforms() {
  const container = document.getElementById("platform-grid");
  if (!container) return;
  container.innerHTML = PLATFORMS.map(p => renderPlatformCard(p)).join("");
  bindPlatformEvents();
}

function renderPlatformCard(platform) {
  const s    = state.platforms[platform.id] || {
    runningCount: 0, busyCount: 0, pendingCount: 0,
    lastMessage: "空闲", currentJobIds: [], lastError: null,
    intervalSeconds: 5, concurrency: 1,
  };
  const hasActivity = s.runningCount > 0;
  const hasError   = !!s.lastError;
  const cardClass  = "platform-card" + (hasActivity ? " active" : "") + (hasError ? " has-error" : "");
  const runningCls = hasActivity ? "live" : "";
  const hasJobs    = (s.currentJobIds || []).length > 0;

  return `
    <div class="${cardClass}" data-platform="${platform.id}">
      <div class="platform-top">
        <div class="platform-name-group">
          <div class="platform-abbr">${esc(platform.abbr)}</div>
          <div class="platform-name">${esc(platform.name)}</div>
        </div>
        <span class="panel-badge ${hasActivity ? 'badge-running' : 'badge-idle'}">
          ${hasActivity ? '运行中' : hasError ? '错误' : '空闲'}
        </span>
      </div>
      <div class="platform-body">
        <div class="stat-strip">
          <div class="mini-stat">
            <div class="mini-label">任务数</div>
            <div class="mini-value ${hasJobs ? runningCls : ''}">${(s.currentJobIds || []).length}</div>
          </div>
          <div class="mini-stat">
            <div class="mini-label">轮询</div>
            <div class="mini-value">${s.intervalSeconds || 5}s</div>
          </div>
          <div class="mini-stat">
            <div class="mini-label">并发</div>
            <div class="mini-value">${s.concurrency || 1}</div>
          </div>
          <div class="mini-stat">
            <div class="mini-label">状态</div>
            <div class="mini-value ${runningCls}" style="font-size:13px">${s.busyCount > 0 ? '忙碌' : hasActivity ? '运行' : '就绪'}</div>
          </div>
        </div>
        <div class="platform-log">
          <div class="log-line" style="color:${hasActivity ? 'var(--text-muted)' : 'var(--text-dim)'}">
            ${esc(s.lastMessage || '// 等待启动')}
          </div>
        </div>
        ${s.lastError ? `<div class="log-line" style="color:var(--danger);font-size:9px">⚠ ${esc(String(s.lastError).slice(0,80))}</div>` : ""}
        <div class="platform-actions">
          <button class="btn-platform start"  data-platform="${platform.id}" data-action="start" ${s.busyCount > 0 ? "disabled" : ""}>▶ 启动</button>
          <button class="btn-platform stop"   data-platform="${platform.id}" data-action="stop"  ${s.runningCount === 0 ? "disabled" : ""}>■ 停止</button>
          <button class="btn-platform cancel" data-platform="${platform.id}" data-action="cancel" ${s.pendingCount === 0 && s.runningCount === 0 ? "disabled" : ""}>✕ 取消</button>
        </div>
      </div>
    </div>
  `;
}

function renderActivity() {
  const container = document.getElementById("log-list");
  if (!container) return;
  const items = state.activity.slice(0, 50);
  container.innerHTML = items.length
    ? items.map(a => `
        <div class="activity-item">
          <div class="activity-meta">${formatAge(a.at)}</div>
          <div class="activity-message ${a.level}">${esc(a.message)}</div>
        </div>`).join("")
    : `<div class="activity-item"><div class="activity-message" style="color:var(--text-dim)">// 暂无活动记录</div></div>`;
}

function renderConfirmToggle() {
  document.getElementById("confirm-track")?.classList.toggle("on", state.confirmBeforeVideoGenerate);
}

/* ── Event binding ─────────────────────────────────────────── */
function bindPlatformEvents() {
  document.querySelectorAll(".btn-platform[data-action]").forEach(btn => {
    btn.addEventListener("click", async () => {
      const platformId = btn.dataset.platform;
      const action    = btn.dataset.action;
      btn.disabled = true;
      try {
        let resp;
        if (action === "start") {
          resp = await bgSend({ type: "dashboard:startPlatform", platformId });
          logActivity(`已启动平台：${platformId}`, "success");
        } else if (action === "stop") {
          resp = await bgSend({ type: "dashboard:stopPlatform", platformId });
          logActivity(`已停止平台：${platformId}`, "warning");
        } else if (action === "cancel") {
          resp = await bgSend({ type: "dashboard:cancelPlatform", platformId });
          logActivity(`已取消平台任务：${platformId}`, "warning");
        }
        if (resp?.state) syncFromBackground(resp.state);
        render();
      } catch (e) {
        logActivity(`操作失败：${e.message}`, "error");
        render();
      } finally {
        btn.disabled = false;
      }
    });
  });
}

function bindGlobalEvents() {
  // Hero: Start All
  document.getElementById("start-all-btn")?.addEventListener("click", async () => {
    const el = document.getElementById("start-all-btn");
    el.disabled = true;
    console.log("[dashboard] start-all-btn clicked");
    try {
      const resp = await bgSend({ type: "dashboard:startAllPlatforms" });
      console.log("[dashboard] bgSend resp:", JSON.stringify(resp));
      logActivity("已启动全部平台", "success");
      if (resp?.state) {
        console.log("[dashboard] syncing state:", JSON.stringify(resp.state.platforms));
        syncFromBackground(resp.state);
      } else {
        console.log("[dashboard] resp.state is undefined or falsy, skipping sync");
      }
      render();
    } catch (e) {
      console.error("[dashboard] bgSend threw:", e);
      logActivity("启动失败：" + e.message, "error");
      render();
    } finally {
      el.disabled = false;
    }
  });

  // Hero: Stop All
  document.getElementById("stop-all-btn")?.addEventListener("click", async () => {
    const el = document.getElementById("stop-all-btn");
    el.disabled = true;
    try {
      const resp = await bgSend({ type: "dashboard:stopAllPlatforms" });
      logActivity("已停止全部平台", "warning");
      if (resp?.state) syncFromBackground(resp.state);
      render();
    } catch (e) {
      logActivity("停止失败：" + e.message, "error");
      render();
    } finally {
      el.disabled = false;
    }
  });

  // Hero: Cancel All
  document.getElementById("cancel-all-btn")?.addEventListener("click", async () => {
    const el = document.getElementById("cancel-all-btn");
    el.disabled = true;
    try {
      const resp = await bgSend({ type: "dashboard:cancelAllPlatforms" });
      logActivity("已取消全部平台任务", "warning");
      if (resp?.state) syncFromBackground(resp.state);
      render();
    } catch (e) {
      logActivity("取消失败：" + e.message, "error");
      render();
    } finally {
      el.disabled = false;
    }
  });

  // Hero: Refresh
  document.getElementById("refresh-btn")?.addEventListener("click", async () => {
    const el = document.getElementById("refresh-btn");
    el.disabled = true;
    try {
      // Refresh background state
      const resp = await bgSend({ type: "dashboard:getState" });
      if (resp?.state) syncFromBackground(resp.state);
      // Refresh bridge job counts
      const bridge = await bridgeState();
      if (bridge?.jobs) syncBridgeJobs(bridge.jobs);
      logActivity("已刷新状态", "success");
      render();
    } catch (e) {
      logActivity("刷新失败：" + e.message, "error");
      render();
    } finally {
      el.disabled = false;
    }
  });

  // Platform select (hero-level filter)
  const select = document.getElementById("platform-select");
  if (select) {
    // Populate select with platform options
    select.innerHTML = `<option value="">— 全部平台 —</option>` +
      PLATFORMS.map(p => `<option value="${p.id}">${p.name}</option>`).join("");
    select.addEventListener("change", () => {
      state.selectedPlatform = select.value;
    });
  }

  // Confirm toggle
  const confirmRow = document.getElementById("confirm-toggle");
  if (confirmRow) {
    confirmRow.addEventListener("click", async () => {
      state.confirmBeforeVideoGenerate = !state.confirmBeforeVideoGenerate;
      renderConfirmToggle();
      await bgSend({
        type: "dashboard:updateGlobalSettings",
        confirmBeforeVideoGenerate: state.confirmBeforeVideoGenerate,
      });
      logActivity(
        state.confirmBeforeVideoGenerate ? "已开启生成前确认" : "已关闭生成前确认",
        "info"
      );
      render();
    });
  }

  // Save settings
  document.getElementById("save-global-btn")?.addEventListener("click", async () => {
    const url      = document.getElementById("server-url")?.value.trim()       || state.serverUrl;
    const interval = parseInt(document.getElementById("platform-interval")?.value)   || 5;
    const concur   = parseInt(document.getElementById("platform-concurrency")?.value) || 1;

    state.serverUrl = url;
    try {
      // Save global settings
      await bgSend({
        type: "dashboard:updateGlobalSettings",
        serverUrl: url,
        confirmBeforeVideoGenerate: state.confirmBeforeVideoGenerate,
      });
      // Save platform settings for each platform
      for (const platform of PLATFORMS) {
        await bgSend({
          type: "dashboard:updatePlatformSettings",
          platformId: platform.id,
          settings: { intervalSeconds: interval, concurrency: concur },
        });
      }
      logActivity("配置已保存", "success");
    } catch (e) {
      logActivity("保存失败：" + e.message, "error");
    }
    // Refresh state
    const resp = await bgSend({ type: "dashboard:getState" });
    if (resp?.state) syncFromBackground(resp.state);
    render();
  });
}

/* ── Message listener: state updates from background ──────── */
chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "dashboard:state") {
    syncFromBackground(message.state);
    render();
  }
});

/* ── Boot ───────────────────────────────────────────────────── */
async function init() {
  console.log("[dashboard] init() starting, chrome.runtime:", typeof chrome?.runtime);
  bindGlobalEvents();
  console.log("[dashboard] bindGlobalEvents done");
  logActivity("控制台初始化完成", "success");

  // Get initial state from background
  const resp = await bgSend({ type: "dashboard:getState" });
  console.log("[dashboard] init bgSend resp:", JSON.stringify(resp));
  if (resp?.ok === false && resp?.error === "extension_unavailable") {
    logActivity("请通过插件页面打开 Dashboard（扩展内部页面才能连接 background）", "error");
    render();
    return;
  }
  if (resp?.state) {
    syncFromBackground(resp.state);
    logActivity("已同步平台状态", "success");
  } else {
    logActivity("无法连接 background.js，扩展可能未加载", "error");
  }

  // Also fetch bridge job stats directly
  const bridge = await bridgeState();
  if (bridge?.jobs) {
    syncBridgeJobs(bridge.jobs);
    logActivity(`已加载 ${bridge.jobs.length} 个任务记录`, "success");
  } else {
    logActivity("无法连接 Bridge 服务器", "error");
  }

  render();

  // Periodic refresh: bridge stats every 5s
  setInterval(async () => {
    const b = await bridgeState();
    if (b?.jobs) { syncBridgeJobs(b.jobs); render(); }
  }, 5000);
}

init();
