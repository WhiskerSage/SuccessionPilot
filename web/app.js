(() => {
  const queryView = (() => {
    try {
      return new URLSearchParams(window.location.search || "").get("view");
    } catch (_err) {
      return "";
    }
  })();
  const startView = String(queryView || document.body.dataset.startView || "overview").trim().toLowerCase();
  const PAGE_SIZE_PREF_KEY = "successor_page_size_by_view";
  const DEFAULT_PAGE_SIZES = Object.freeze({
    overview: 10,
    leads: 30,
    summary: 20,
  });
  const ALLOWED_PAGE_SIZES = [10, 20, 30, 50];
  const QUICK_EDIT_FIELDS = ["title", "position", "company", "location", "requirements", "summary"];

  const state = {
    leads: [],
    selectedNoteId: "",
    loading: false,
    skin: "business-blue",
    search: "",
    view: startView || "overview",
    runItems: [],
    performance: null,
    selectedRunId: "",
    runDetail: null,
    runtime: null,
    config: null,
    prevJobRunning: false,
    leadFilters: {
      status: "all",
      dedupe: "all",
    },
    retryQueueFilters: {
      status: "all",
      queueType: "all",
    },
    retryQueueData: null,
    leadEditSaving: false,
    pagination: {
      page: 1,
      pageSize: 30,
      total: 0,
      totalPages: 1,
    },
    pageSizePrefs: { ...DEFAULT_PAGE_SIZES },
    retryQueueUnavailable: false,
  };

  const dom = {
    toast: document.getElementById("toast"),
    kpiRaw: document.getElementById("kpiRaw"),
    kpiSummary: document.getElementById("kpiSummary"),
    kpiJobs: document.getElementById("kpiJobs"),
    kpiSend: document.getElementById("kpiSend"),
    latestRunId: document.getElementById("latestRunId"),
    latestRunTime: document.getElementById("latestRunTime"),
    digestMinutes: document.getElementById("digestMinutes"),
    daemonQuickState: document.getElementById("daemonQuickState"),
    jobQuickState: document.getElementById("jobQuickState"),
    leadCount: document.getElementById("leadCount"),
    leadBody: document.getElementById("leadBody"),
    detailBox: document.getElementById("detailBox"),
    leadHeadRow: document.querySelector(".table-wrap thead tr"),
    leadPanelTitle: document.querySelector(".table-panel .head-row h3"),
    detailPanelTitle: document.querySelector(".detail-panel .head-row h3"),
    detailPanelChip: document.querySelector(".detail-panel .head-row .chip"),
    runList: document.getElementById("runList"),
    searchInput: document.getElementById("searchInput"),
    searchWrap: document.querySelector(".toolbar .search"),
    refreshBtn: document.getElementById("refreshBtn"),
    skinBtn: document.getElementById("skinBtn"),
    navItems: document.querySelectorAll(".nav-link[data-page]"),
    workspace: document.getElementById("workspace"),
    controlSection: document.getElementById("controlSection"),
    leadPrevBtn: document.getElementById("leadPrevBtn"),
    leadNextBtn: document.getElementById("leadNextBtn"),
    leadPageInfo: document.getElementById("leadPageInfo"),
    leadPageSize: document.getElementById("leadPageSize"),
    leadPager: document.getElementById("leadPager"),
    runModeSelect: document.getElementById("runModeSelect"),
    sendLatestInput: document.getElementById("sendLatestInput"),
    loginTimeoutInput: document.getElementById("loginTimeoutInput"),
    runOnceBtn: document.getElementById("runOnceBtn"),
    sendLatestBtn: document.getElementById("sendLatestBtn"),
    xhsLoginBtn: document.getElementById("xhsLoginBtn"),
    xhsStatusBtn: document.getElementById("xhsStatusBtn"),
    daemonModeSelect: document.getElementById("daemonModeSelect"),
    daemonIntervalInput: document.getElementById("daemonIntervalInput"),
    startDaemonBtn: document.getElementById("startDaemonBtn"),
    stopDaemonBtn: document.getElementById("stopDaemonBtn"),
    stopJobBtn: document.getElementById("stopJobBtn"),
    daemonStateText: document.getElementById("daemonStateText"),
    runtimeDaemonState: document.getElementById("runtimeDaemonState"),
    runtimeJobState: document.getElementById("runtimeJobState"),
    runtimeUpdatedAt: document.getElementById("runtimeUpdatedAt"),
    runtimeLog: document.getElementById("runtimeLog"),
    reloadConfigBtn: document.getElementById("reloadConfigBtn"),
    saveConfigBtn: document.getElementById("saveConfigBtn"),
    cfgKeyword: document.getElementById("cfgKeyword"),
    cfgXhsAccount: document.getElementById("cfgXhsAccount"),
    cfgXhsAccountDir: document.getElementById("cfgXhsAccountDir"),
    cfgSearchSort: document.getElementById("cfgSearchSort"),
    cfgMaxResults: document.getElementById("cfgMaxResults"),
    cfgMaxDetailFetch: document.getElementById("cfgMaxDetailFetch"),
    cfgDetailWorkers: document.getElementById("cfgDetailWorkers"),
    cfgProcessWorkers: document.getElementById("cfgProcessWorkers"),
    cfgAppInterval: document.getElementById("cfgAppInterval"),
    cfgAgentMode: document.getElementById("cfgAgentMode"),
    cfgNotifyMode: document.getElementById("cfgNotifyMode"),
    cfgDigestInterval: document.getElementById("cfgDigestInterval"),
    cfgDigestTop: document.getElementById("cfgDigestTop"),
    cfgDigestNoNew: document.getElementById("cfgDigestNoNew"),
    cfgEmailEnabled: document.getElementById("cfgEmailEnabled"),
    cfgWechatEnabled: document.getElementById("cfgWechatEnabled"),
    cfgLlmEnabled: document.getElementById("cfgLlmEnabled"),
    cfgLlmModel: document.getElementById("cfgLlmModel"),
    cfgLlmBaseUrl: document.getElementById("cfgLlmBaseUrl"),
    cfgAlertEnabled: document.getElementById("cfgAlertEnabled"),
    cfgAlertCooldown: document.getElementById("cfgAlertCooldown"),
    cfgAlertFetchShortWindowRuns: document.getElementById("cfgAlertFetchShortWindowRuns"),
    cfgAlertFetchStreak: document.getElementById("cfgAlertFetchStreak"),
    cfgAlertFetchShortMinRuns: document.getElementById("cfgAlertFetchShortMinRuns"),
    cfgAlertFetchLongWindowRuns: document.getElementById("cfgAlertFetchLongWindowRuns"),
    cfgAlertFetchLongThreshold: document.getElementById("cfgAlertFetchLongThreshold"),
    cfgAlertFetchLongMinRuns: document.getElementById("cfgAlertFetchLongMinRuns"),
    cfgAlertLlmShortWindowRuns: document.getElementById("cfgAlertLlmShortWindowRuns"),
    cfgAlertLlmTimeoutRate: document.getElementById("cfgAlertLlmTimeoutRate"),
    cfgAlertLlmTimeoutMinCalls: document.getElementById("cfgAlertLlmTimeoutMinCalls"),
    cfgAlertLlmLongWindowRuns: document.getElementById("cfgAlertLlmLongWindowRuns"),
    cfgAlertLlmLongThreshold: document.getElementById("cfgAlertLlmLongThreshold"),
    cfgAlertLlmLongMinSamples: document.getElementById("cfgAlertLlmLongMinSamples"),
    cfgAlertDetailShortWindowRuns: document.getElementById("cfgAlertDetailShortWindowRuns"),
    cfgAlertDetailMissingRate: document.getElementById("cfgAlertDetailMissingRate"),
    cfgAlertDetailMissingMinSamples: document.getElementById("cfgAlertDetailMissingMinSamples"),
    cfgAlertDetailLongWindowRuns: document.getElementById("cfgAlertDetailLongWindowRuns"),
    cfgAlertDetailLongThreshold: document.getElementById("cfgAlertDetailLongThreshold"),
    cfgAlertDetailLongMinSamples: document.getElementById("cfgAlertDetailLongMinSamples"),
    cfgAlertChannels: document.getElementById("cfgAlertChannels"),
    wizardGuideBadge: document.getElementById("wizardGuideBadge"),
    wizardGuideSteps: document.getElementById("wizardGuideSteps"),
    wizardApplyBtn: document.getElementById("wizardApplyBtn"),
    wizardCheckBtn: document.getElementById("wizardCheckBtn"),
    wizardMarkDoneBtn: document.getElementById("wizardMarkDoneBtn"),
    wizardCheckSummary: document.getElementById("wizardCheckSummary"),
    wizardCheckList: document.getElementById("wizardCheckList"),
    resumeFileInput: document.getElementById("resumeFileInput"),
    resumeParseBtn: document.getElementById("resumeParseBtn"),
    resumeUploadBtn: document.getElementById("resumeUploadBtn"),
    resumeSourcePath: document.getElementById("resumeSourcePath"),
    resumeTextPath: document.getElementById("resumeTextPath"),
    resumeTextArea: document.getElementById("resumeTextArea"),
    resumeChars: document.getElementById("resumeChars"),
    resumeSourceExists: document.getElementById("resumeSourceExists"),
    leadStatusFilter: document.getElementById("leadStatusFilter"),
    leadDedupeFilter: document.getElementById("leadDedupeFilter"),
    runtimeProgressWrap: document.getElementById("runtimeProgressWrap"),
    runtimeProgressBar: document.getElementById("runtimeProgressBar"),
    runtimeProgressText: document.getElementById("runtimeProgressText"),
    runDetailBox: document.getElementById("runDetailBox"),
    retryQueueStatusFilter: document.getElementById("retryQueueStatusFilter"),
    retryQueueTypeFilter: document.getElementById("retryQueueTypeFilter"),
    retryQueueRefreshBtn: document.getElementById("retryQueueRefreshBtn"),
    retryQueueReplayBtn: document.getElementById("retryQueueReplayBtn"),
    retryQueueBody: document.getElementById("retryQueueBody"),
    retryQueueSummary: document.getElementById("retryQueueSummary"),
    retryDeadBody: document.getElementById("retryDeadBody"),
    retryDeadSummary: document.getElementById("retryDeadSummary"),
    perfSample: document.getElementById("perfSample"),
    perfTotalAvg: document.getElementById("perfTotalAvg"),
    perfTotalP50: document.getElementById("perfTotalP50"),
    perfTotalP95: document.getElementById("perfTotalP95"),
    perfStageFailRate: document.getElementById("perfStageFailRate"),
    perfDetailSuccessRate: document.getElementById("perfDetailSuccessRate"),
    perfLlmFailTotal: document.getElementById("perfLlmFailTotal"),
    perfFetchFailTotal: document.getElementById("perfFetchFailTotal"),
    perfAlertTriggeredTotal: document.getElementById("perfAlertTriggeredTotal"),
    perfAlertNotifiedTotal: document.getElementById("perfAlertNotifiedTotal"),
    perfAlertRunRate: document.getElementById("perfAlertRunRate"),
    perfSlowStages: document.getElementById("perfSlowStages"),
    perfErrorCodes: document.getElementById("perfErrorCodes"),
    perfAlertCodes: document.getElementById("perfAlertCodes"),
    qualityRawTotal: document.getElementById("qualityRawTotal"),
    qualityJobsTotal: document.getElementById("qualityJobsTotal"),
    qualityDetailFillRate: document.getElementById("qualityDetailFillRate"),
    qualityStructuredRate: document.getElementById("qualityStructuredRate"),
    qualityCompanyRate: document.getElementById("qualityCompanyRate"),
    qualityPositionRate: document.getElementById("qualityPositionRate"),
    qualityLocationRate: document.getElementById("qualityLocationRate"),
    qualityRequirementsRate: document.getElementById("qualityRequirementsRate"),
    qualityExtractionHitRate: document.getElementById("qualityExtractionHitRate"),
    qualityLlmSuccessRate: document.getElementById("qualityLlmSuccessRate"),
    qualityRecentDetailRate: document.getElementById("qualityRecentDetailRate"),
    qualityMissingFields: document.getElementById("qualityMissingFields"),
    qualityTrend: document.getElementById("qualityTrend"),
  };

  let selectedResumeFile = null;
  let workspaceVue = null;
  let workspaceVueApp = null;
  let retryQueueWarningShown = false;
  const optionalLoadWarned = {
    config: false,
    resume: false,
  };

  const SKINS = ["business-blue", "graphite-office"];
  const WIZARD_DONE_KEY = "successor_setup_wizard_done";
  const API_BASES = (() => {
    const candidates = ["", "http://127.0.0.1:8787", "http://localhost:8787"];
    if (window.location.protocol === "file:") {
      return candidates.filter((item) => item);
    }
    return candidates;
  })();
  const DEFAULT_DETAIL_LEADS = `
    <h4>请选择一条线索</h4>
    <p>这里会展示岗位摘要、JD、评论预览和原帖详情内容。</p>
  `;
  const DEFAULT_DETAIL_SUMMARY = `
    <h4>请选择一条摘要</h4>
    <p>摘要中心默认仅展示岗位、公司、岗位要求与摘要，不展示原帖噪声字段。</p>
  `;

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function toText(value, fallback = "-") {
    const text = String(value ?? "").trim();
    return text || fallback;
  }

  function toInt(value, fallback = 0) {
    const n = Number(value);
    if (!Number.isFinite(n)) {
      return fallback;
    }
    return Math.trunc(n);
  }

  function toFloat(value, fallback = 0) {
    const n = Number(value);
    if (!Number.isFinite(n)) {
      return fallback;
    }
    return n;
  }

  function showToast(message, type = "info") {
    if (!dom.toast) return;
    dom.toast.className = `toast show ${type}`;
    dom.toast.textContent = String(message || "");
    window.clearTimeout(showToast._timer);
    showToast._timer = window.setTimeout(() => {
      dom.toast.className = "toast";
    }, 2600);
  }

  function fmtTime(value) {
    const text = String(value ?? "").trim();
    if (!text) return "-";
    if (/^\d{4}-\d{2}-\d{2}T/.test(text)) {
      // Legacy rows may persist UTC timestamps without timezone suffix.
      // Normalize them as UTC to avoid local-time misinterpretation.
      const iso = /([zZ]|[+-]\d{2}:\d{2})$/.test(text) ? text : `${text}Z`;
      const ts = Date.parse(iso);
      if (!Number.isNaN(ts)) {
        const dt = new Date(ts);
        const pad = (n) => String(n).padStart(2, "0");
        return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())} ${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
      }
    }
    return text;
  }

  function fmtInt(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "0";
    return n.toLocaleString("zh-CN");
  }

  function fmtMs(value) {
    const ms = Math.max(0, toInt(value, 0));
    if (!ms) return "-";
    if (ms < 1000) return `${ms}ms`;
    const seconds = ms / 1000;
    if (seconds < 10) return `${seconds.toFixed(1)}s`;
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const minutes = Math.floor(seconds / 60);
    const remain = Math.round(seconds % 60);
    if (!remain) return `${minutes}m`;
    return `${minutes}m${String(remain).padStart(2, "0")}s`;
  }

  function statusBadge(status, likeCount, commentCount) {
    const score = Number(likeCount || 0) + Number(commentCount || 0) * 2;
    let cls = "";
    if (String(status).includes("高")) {
      cls = "hot";
    } else if (String(status).includes("可") || String(status).includes("待")) {
      cls = "ok";
    }
    return `<span class="badge ${cls}" title="热度分: ${escapeHtml(score)}">${escapeHtml(toText(status))}</span>`;
  }

  function buildApiUrl(path, base) {
    if (!base) return path;
    return `${base}${path}`;
  }

  async function apiRequest(path, options = {}) {
    let lastError = null;
    for (const base of API_BASES) {
      const url = buildApiUrl(path, base);
      try {
        const resp = await fetch(url, options);
        const contentType = resp.headers.get("Content-Type") || "";
        const isJson = contentType.includes("application/json");
        let payload = null;
        let textBody = "";
        if (isJson) {
          try {
            payload = await resp.json();
          } catch (e) {
            payload = null;
          }
        } else {
          textBody = await resp.text();
        }
        if (!resp.ok) {
          const errorObj = payload && typeof payload === "object" ? payload.error : null;
          const code = errorObj && errorObj.code ? String(errorObj.code) : "";
          const message = errorObj && errorObj.message ? String(errorObj.message) : (textBody || `${resp.status} ${resp.statusText}`);
          const reason = errorObj && errorObj.reason ? String(errorObj.reason) : "";
          const fix = errorObj && errorObj.fix_command ? String(errorObj.fix_command) : "";
          const parts = [];
          if (code) parts.push(`[${code}]`);
          parts.push(message);
          if (reason && reason !== message) parts.push(`原因: ${reason}`);
          if (fix) parts.push(`修复: ${fix}`);
          throw new Error(parts.join(" | ").trim());
        }
        if (isJson) {
          if (payload && typeof payload === "object" && payload.ok === false && payload.error) {
            const err = payload.error || {};
            const code = err.code ? `[${err.code}] ` : "";
            const message = String(err.message || "request failed");
            const reason = err.reason ? ` | 原因: ${err.reason}` : "";
            const fix = err.fix_command ? ` | 修复: ${err.fix_command}` : "";
            throw new Error(`${code}${message}${reason}${fix}`.trim());
          }
          return payload || {};
        }
        return {};
      } catch (err) {
        lastError = err;
      }
    }
    const reason = lastError instanceof Error ? lastError.message : String(lastError || "unknown error");
    throw new Error(`API unavailable (${reason}). 请启动 dashboard: http://127.0.0.1:8787`);
  }

  async function fetchJson(path) {
    return apiRequest(path, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
  }

  async function postJson(path, payload) {
    return apiRequest(path, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload || {}),
    });
  }

  async function postForm(path, formData) {
    return apiRequest(path, {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
      body: formData,
    });
  }

  function toBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result || "");
        const commaIndex = result.indexOf(",");
        if (commaIndex < 0) {
          resolve(result);
          return;
        }
        resolve(result.slice(commaIndex + 1));
      };
      reader.onerror = () => reject(reader.error || new Error("read file failed"));
      reader.readAsDataURL(file);
    });
  }

  function isApiNotFoundError(err) {
    const msg = String(err instanceof Error ? err.message : err || "")
      .toLowerCase()
      .trim();
    if (!msg) return false;
    return msg.includes("404") || msg.includes("not_found");
  }

  function renderRetryQueueUnavailable(message) {
    const reason = String(message || "当前后端未启用重试队列接口").trim();
    if (dom.retryQueueSummary) dom.retryQueueSummary.textContent = "重试队列不可用";
    if (dom.retryQueueBody) {
      dom.retryQueueBody.innerHTML = `<tr><td colspan="7" class="table-tip">${escapeHtml(reason)}</td></tr>`;
    }
    if (dom.retryDeadSummary) dom.retryDeadSummary.textContent = "-";
    if (dom.retryDeadBody) {
      dom.retryDeadBody.innerHTML = '<tr><td colspan="4" class="table-tip">暂无死信记录</td></tr>';
    }
  }

  function defaultPageSizeForView(view) {
    if (view === "overview") return 10;
    if (view === "summary") return 20;
    return 30;
  }

  function pageSizeForView(view) {
    const key = String(view || "").trim().toLowerCase();
    const fallback = defaultPageSizeForView(key);
    const preferred = toInt(state.pageSizePrefs && state.pageSizePrefs[key], fallback);
    if (ALLOWED_PAGE_SIZES.includes(preferred)) {
      return preferred;
    }
    return fallback;
  }

  function loadPageSizePrefs() {
    let parsed = {};
    try {
      const raw = localStorage.getItem(PAGE_SIZE_PREF_KEY);
      if (raw) {
        const value = JSON.parse(raw);
        if (value && typeof value === "object") {
          parsed = value;
        }
      }
    } catch (_err) {
      parsed = {};
    }
    state.pageSizePrefs = { ...DEFAULT_PAGE_SIZES };
    Object.keys(DEFAULT_PAGE_SIZES).forEach((key) => {
      const value = toInt(parsed[key], DEFAULT_PAGE_SIZES[key]);
      if (ALLOWED_PAGE_SIZES.includes(value)) {
        state.pageSizePrefs[key] = value;
      }
    });
  }

  function savePageSizePrefs() {
    try {
      localStorage.setItem(PAGE_SIZE_PREF_KEY, JSON.stringify(state.pageSizePrefs || {}));
    } catch (_err) {}
  }

  function rememberPageSizeForView(view, pageSize) {
    const key = String(view || "").trim().toLowerCase();
    if (!(key in DEFAULT_PAGE_SIZES)) return;
    const value = toInt(pageSize, defaultPageSizeForView(key));
    if (!ALLOWED_PAGE_SIZES.includes(value)) return;
    state.pageSizePrefs[key] = value;
    savePageSizePrefs();
  }

  function isWorkspaceView(view) {
    return view !== "control";
  }

  function isSummaryView() {
    return state.view === "summary";
  }

  function tableColumnCount() {
    return isSummaryView() ? 4 : 5;
  }

  function defaultDetailHtml() {
    return isSummaryView() ? DEFAULT_DETAIL_SUMMARY : DEFAULT_DETAIL_LEADS;
  }

  function refreshDynamicDomRefs() {
    dom.cfgDetailWorkers = document.getElementById("cfgDetailWorkers");
    dom.cfgProcessWorkers = document.getElementById("cfgProcessWorkers");
    dom.cfgAlertEnabled = document.getElementById("cfgAlertEnabled");
    dom.cfgAlertCooldown = document.getElementById("cfgAlertCooldown");
    dom.cfgAlertFetchShortWindowRuns = document.getElementById("cfgAlertFetchShortWindowRuns");
    dom.cfgAlertFetchStreak = document.getElementById("cfgAlertFetchStreak");
    dom.cfgAlertFetchShortMinRuns = document.getElementById("cfgAlertFetchShortMinRuns");
    dom.cfgAlertFetchLongWindowRuns = document.getElementById("cfgAlertFetchLongWindowRuns");
    dom.cfgAlertFetchLongThreshold = document.getElementById("cfgAlertFetchLongThreshold");
    dom.cfgAlertFetchLongMinRuns = document.getElementById("cfgAlertFetchLongMinRuns");
    dom.cfgAlertLlmShortWindowRuns = document.getElementById("cfgAlertLlmShortWindowRuns");
    dom.cfgAlertLlmTimeoutRate = document.getElementById("cfgAlertLlmTimeoutRate");
    dom.cfgAlertLlmTimeoutMinCalls = document.getElementById("cfgAlertLlmTimeoutMinCalls");
    dom.cfgAlertLlmLongWindowRuns = document.getElementById("cfgAlertLlmLongWindowRuns");
    dom.cfgAlertLlmLongThreshold = document.getElementById("cfgAlertLlmLongThreshold");
    dom.cfgAlertLlmLongMinSamples = document.getElementById("cfgAlertLlmLongMinSamples");
    dom.cfgAlertDetailShortWindowRuns = document.getElementById("cfgAlertDetailShortWindowRuns");
    dom.cfgAlertDetailMissingRate = document.getElementById("cfgAlertDetailMissingRate");
    dom.cfgAlertDetailMissingMinSamples = document.getElementById("cfgAlertDetailMissingMinSamples");
    dom.cfgAlertDetailLongWindowRuns = document.getElementById("cfgAlertDetailLongWindowRuns");
    dom.cfgAlertDetailLongThreshold = document.getElementById("cfgAlertDetailLongThreshold");
    dom.cfgAlertDetailLongMinSamples = document.getElementById("cfgAlertDetailLongMinSamples");
    dom.cfgAlertChannels = document.getElementById("cfgAlertChannels");
    dom.leadStatusFilter = document.getElementById("leadStatusFilter");
    dom.leadDedupeFilter = document.getElementById("leadDedupeFilter");
    dom.runtimeProgressWrap = document.getElementById("runtimeProgressWrap");
    dom.runtimeProgressBar = document.getElementById("runtimeProgressBar");
    dom.runtimeProgressText = document.getElementById("runtimeProgressText");
    dom.runDetailBox = document.getElementById("runDetailBox");
    dom.retryQueueStatusFilter = document.getElementById("retryQueueStatusFilter");
    dom.retryQueueTypeFilter = document.getElementById("retryQueueTypeFilter");
    dom.retryQueueRefreshBtn = document.getElementById("retryQueueRefreshBtn");
    dom.retryQueueReplayBtn = document.getElementById("retryQueueReplayBtn");
    dom.retryQueueBody = document.getElementById("retryQueueBody");
    dom.retryQueueSummary = document.getElementById("retryQueueSummary");
    dom.retryDeadBody = document.getElementById("retryDeadBody");
    dom.retryDeadSummary = document.getElementById("retryDeadSummary");
    dom.perfSample = document.getElementById("perfSample");
    dom.perfTotalAvg = document.getElementById("perfTotalAvg");
    dom.perfTotalP50 = document.getElementById("perfTotalP50");
    dom.perfTotalP95 = document.getElementById("perfTotalP95");
    dom.perfStageFailRate = document.getElementById("perfStageFailRate");
    dom.perfDetailSuccessRate = document.getElementById("perfDetailSuccessRate");
    dom.perfLlmFailTotal = document.getElementById("perfLlmFailTotal");
    dom.perfFetchFailTotal = document.getElementById("perfFetchFailTotal");
    dom.perfAlertTriggeredTotal = document.getElementById("perfAlertTriggeredTotal");
    dom.perfAlertNotifiedTotal = document.getElementById("perfAlertNotifiedTotal");
    dom.perfAlertRunRate = document.getElementById("perfAlertRunRate");
    dom.perfSlowStages = document.getElementById("perfSlowStages");
    dom.perfErrorCodes = document.getElementById("perfErrorCodes");
    dom.perfAlertCodes = document.getElementById("perfAlertCodes");
    dom.qualityRawTotal = document.getElementById("qualityRawTotal");
    dom.qualityJobsTotal = document.getElementById("qualityJobsTotal");
    dom.qualityDetailFillRate = document.getElementById("qualityDetailFillRate");
    dom.qualityStructuredRate = document.getElementById("qualityStructuredRate");
    dom.qualityCompanyRate = document.getElementById("qualityCompanyRate");
    dom.qualityPositionRate = document.getElementById("qualityPositionRate");
    dom.qualityLocationRate = document.getElementById("qualityLocationRate");
    dom.qualityRequirementsRate = document.getElementById("qualityRequirementsRate");
    dom.qualityExtractionHitRate = document.getElementById("qualityExtractionHitRate");
    dom.qualityLlmSuccessRate = document.getElementById("qualityLlmSuccessRate");
    dom.qualityRecentDetailRate = document.getElementById("qualityRecentDetailRate");
    dom.qualityMissingFields = document.getElementById("qualityMissingFields");
    dom.qualityTrend = document.getElementById("qualityTrend");
  }

  function ensureEnhancedUi() {
    const tableHead = document.querySelector(".table-panel .head-row");
    if (tableHead && !document.getElementById("leadFiltersRow")) {
      const row = document.createElement("div");
      row.id = "leadFiltersRow";
      row.className = "lead-filters-row";
      row.innerHTML = `
        <label class="mini-field">
          <span>状态</span>
          <select id="leadStatusFilter">
            <option value="all">全部</option>
            <option value="high_priority">高优先级</option>
            <option value="actionable">可推进</option>
            <option value="pending_review">待复核</option>
            <option value="new_lead">新线索</option>
          </select>
        </label>
        <label class="mini-field">
          <span>去重状态</span>
          <select id="leadDedupeFilter">
            <option value="all">全部</option>
            <option value="new">新增</option>
            <option value="updated">已更新</option>
          </select>
        </label>
      `;
      tableHead.appendChild(row);
    }

    const runtimeLog = dom.runtimeLog;
    const runtimeCard = runtimeLog ? runtimeLog.closest(".ops-card") : null;
    if (runtimeCard && !document.getElementById("runtimeProgressWrap")) {
      const wrap = document.createElement("div");
      wrap.id = "runtimeProgressWrap";
      wrap.className = "runtime-progress hidden";
      wrap.innerHTML = `
        <div class="runtime-progress-track"><div id="runtimeProgressBar" class="runtime-progress-bar"></div></div>
        <div id="runtimeProgressText" class="runtime-progress-text">-</div>
      `;
      const meta = runtimeCard.querySelector(".runtime-meta");
      if (meta && meta.nextSibling) {
        runtimeCard.insertBefore(wrap, meta.nextSibling);
      } else {
        runtimeCard.appendChild(wrap);
      }
    }

    const runsBox = document.querySelector(".runs-box");
    if (runsBox && !document.getElementById("runDetailBox")) {
      const detail = document.createElement("div");
      detail.id = "runDetailBox";
      detail.className = "run-detail-box";
      detail.innerHTML = "<p class='muted'>点击一条运行记录后显示详细阶段、错误和诊断信息。</p>";
      runsBox.appendChild(detail);
    }

    const opsGrid = document.querySelector("#controlSection .ops-grid");
    if (opsGrid && !document.getElementById("retryQueueCard")) {
      const card = document.createElement("article");
      card.id = "retryQueueCard";
      card.className = "ops-card ops-span-2";
      card.innerHTML = `
        <div class="head-row">
          <h4>失败重试队列</h4>
          <span id="retryQueueSummary" class="count">-</span>
        </div>
        <div class="retry-toolbar">
          <label class="mini-field">
            <span>状态</span>
            <select id="retryQueueStatusFilter">
              <option value="all">全部</option>
              <option value="pending">待执行</option>
              <option value="running">执行中</option>
              <option value="done">已完成</option>
              <option value="dead_letter">死信</option>
              <option value="dropped">已丢弃</option>
            </select>
          </label>
          <label class="mini-field">
            <span>类型</span>
            <select id="retryQueueTypeFilter">
              <option value="all">全部</option>
              <option value="fetch">抓取</option>
              <option value="llm_timeout">LLM超时</option>
              <option value="email">邮件</option>
            </select>
          </label>
          <button id="retryQueueRefreshBtn" class="btn ghost" type="button">刷新队列</button>
          <button id="retryQueueReplayBtn" class="btn ghost" type="button">触发待执行重试</button>
        </div>
        <div class="table-wrap retry-table-wrap">
          <table class="retry-table">
            <thead>
              <tr>
                <th>类型/动作</th>
                <th>状态</th>
                <th>尝试</th>
                <th>错误码/最近错误</th>
                <th>耗时/Trace</th>
                <th>更新时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody id="retryQueueBody">
              <tr><td colspan="7" class="table-tip">暂无队列数据</td></tr>
            </tbody>
          </table>
        </div>
        <div class="retry-dead-wrap">
          <div class="head-row">
            <h4>死信记录</h4>
            <span id="retryDeadSummary" class="count">-</span>
          </div>
          <div class="table-wrap retry-dead-table-wrap">
            <table class="retry-table retry-dead-table">
              <thead>
                <tr>
                  <th>类型/动作</th>
                  <th>尝试</th>
                  <th>错误码/原因</th>
                  <th>死信时间</th>
                </tr>
              </thead>
              <tbody id="retryDeadBody">
                <tr><td colspan="4" class="table-tip">暂无死信记录</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      `;
      opsGrid.appendChild(card);
    }

    const configForm = document.getElementById("configForm");
    if (configForm && !document.getElementById("cfgDetailWorkers")) {
      const detailField = document.createElement("label");
      detailField.className = "field";
      detailField.innerHTML = `
        <span>详情并行数</span>
        <input id="cfgDetailWorkers" type="number" min="1" max="8" />
      `;
      const processField = document.createElement("label");
      processField.className = "field";
      processField.innerHTML = `
        <span>处理并行数</span>
        <input id="cfgProcessWorkers" type="number" min="1" max="12" />
      `;
      const anchor = document.getElementById("cfgMaxDetailFetch");
      const anchorField = anchor ? anchor.closest(".field") : null;
      if (anchorField && anchorField.parentNode) {
        anchorField.parentNode.insertBefore(detailField, anchorField.nextSibling);
        anchorField.parentNode.insertBefore(processField, detailField.nextSibling);
      } else {
        configForm.appendChild(detailField);
        configForm.appendChild(processField);
      }
    }
    if (configForm && !document.getElementById("cfgAlertEnabled")) {
      const alertEnabledField = document.createElement("label");
      alertEnabledField.className = "field checkbox";
      alertEnabledField.innerHTML = `
        <input id="cfgAlertEnabled" type="checkbox" />
        <span>启用阈值告警</span>
      `;
      const alertCooldownField = document.createElement("label");
      alertCooldownField.className = "field";
      alertCooldownField.innerHTML = `
        <span>告警冷却(分钟)</span>
        <input id="cfgAlertCooldown" type="number" min="1" max="1440" />
      `;
      const alertFetchShortWindowField = document.createElement("label");
      alertFetchShortWindowField.className = "field";
      alertFetchShortWindowField.innerHTML = `
        <span>抓取短窗轮数</span>
        <input id="cfgAlertFetchShortWindowRuns" type="number" min="1" max="30" />
      `;
      const alertFetchField = document.createElement("label");
      alertFetchField.className = "field";
      alertFetchField.innerHTML = `
        <span>抓取短窗阈值</span>
        <input id="cfgAlertFetchStreak" type="number" min="1" max="20" />
      `;
      const alertFetchShortMinField = document.createElement("label");
      alertFetchShortMinField.className = "field";
      alertFetchShortMinField.innerHTML = `
        <span>抓取短窗最小轮数</span>
        <input id="cfgAlertFetchShortMinRuns" type="number" min="1" max="30" />
      `;
      const alertFetchLongWindowField = document.createElement("label");
      alertFetchLongWindowField.className = "field";
      alertFetchLongWindowField.innerHTML = `
        <span>抓取长窗轮数</span>
        <input id="cfgAlertFetchLongWindowRuns" type="number" min="1" max="60" />
      `;
      const alertFetchLongThresholdField = document.createElement("label");
      alertFetchLongThresholdField.className = "field";
      alertFetchLongThresholdField.innerHTML = `
        <span>抓取长窗阈值(平均)</span>
        <input id="cfgAlertFetchLongThreshold" type="number" min="1" max="20" step="0.1" />
      `;
      const alertFetchLongMinField = document.createElement("label");
      alertFetchLongMinField.className = "field";
      alertFetchLongMinField.innerHTML = `
        <span>抓取长窗最小轮数</span>
        <input id="cfgAlertFetchLongMinRuns" type="number" min="1" max="60" />
      `;
      const alertLlmShortWindowField = document.createElement("label");
      alertLlmShortWindowField.className = "field";
      alertLlmShortWindowField.innerHTML = `
        <span>LLM短窗轮数</span>
        <input id="cfgAlertLlmShortWindowRuns" type="number" min="1" max="30" />
      `;
      const alertLlmRateField = document.createElement("label");
      alertLlmRateField.className = "field";
      alertLlmRateField.innerHTML = `
        <span>LLM短窗阈值(%)</span>
        <input id="cfgAlertLlmTimeoutRate" type="number" min="1" max="100" />
      `;
      const alertLlmCallsField = document.createElement("label");
      alertLlmCallsField.className = "field";
      alertLlmCallsField.innerHTML = `
        <span>LLM短窗最小样本</span>
        <input id="cfgAlertLlmTimeoutMinCalls" type="number" min="1" max="500" />
      `;
      const alertLlmLongWindowField = document.createElement("label");
      alertLlmLongWindowField.className = "field";
      alertLlmLongWindowField.innerHTML = `
        <span>LLM长窗轮数</span>
        <input id="cfgAlertLlmLongWindowRuns" type="number" min="1" max="60" />
      `;
      const alertLlmLongThresholdField = document.createElement("label");
      alertLlmLongThresholdField.className = "field";
      alertLlmLongThresholdField.innerHTML = `
        <span>LLM长窗阈值(%)</span>
        <input id="cfgAlertLlmLongThreshold" type="number" min="1" max="100" />
      `;
      const alertLlmLongMinSamplesField = document.createElement("label");
      alertLlmLongMinSamplesField.className = "field";
      alertLlmLongMinSamplesField.innerHTML = `
        <span>LLM长窗最小样本</span>
        <input id="cfgAlertLlmLongMinSamples" type="number" min="1" max="1000" />
      `;
      const alertDetailShortWindowField = document.createElement("label");
      alertDetailShortWindowField.className = "field";
      alertDetailShortWindowField.innerHTML = `
        <span>详情短窗轮数</span>
        <input id="cfgAlertDetailShortWindowRuns" type="number" min="1" max="30" />
      `;
      const alertDetailRateField = document.createElement("label");
      alertDetailRateField.className = "field";
      alertDetailRateField.innerHTML = `
        <span>详情短窗阈值(%)</span>
        <input id="cfgAlertDetailMissingRate" type="number" min="1" max="100" />
      `;
      const alertDetailSamplesField = document.createElement("label");
      alertDetailSamplesField.className = "field";
      alertDetailSamplesField.innerHTML = `
        <span>详情短窗最小样本</span>
        <input id="cfgAlertDetailMissingMinSamples" type="number" min="1" max="500" />
      `;
      const alertDetailLongWindowField = document.createElement("label");
      alertDetailLongWindowField.className = "field";
      alertDetailLongWindowField.innerHTML = `
        <span>详情长窗轮数</span>
        <input id="cfgAlertDetailLongWindowRuns" type="number" min="1" max="60" />
      `;
      const alertDetailLongThresholdField = document.createElement("label");
      alertDetailLongThresholdField.className = "field";
      alertDetailLongThresholdField.innerHTML = `
        <span>详情长窗阈值(%)</span>
        <input id="cfgAlertDetailLongThreshold" type="number" min="1" max="100" />
      `;
      const alertDetailLongMinSamplesField = document.createElement("label");
      alertDetailLongMinSamplesField.className = "field";
      alertDetailLongMinSamplesField.innerHTML = `
        <span>详情长窗最小样本</span>
        <input id="cfgAlertDetailLongMinSamples" type="number" min="1" max="1000" />
      `;
      const alertChannelsField = document.createElement("label");
      alertChannelsField.className = "field span-2";
      alertChannelsField.innerHTML = `
        <span>告警通道(逗号分隔)</span>
        <input id="cfgAlertChannels" type="text" placeholder="留空=复用 digest_channels" />
      `;
      configForm.appendChild(alertEnabledField);
      configForm.appendChild(alertCooldownField);
      configForm.appendChild(alertFetchField);
      configForm.appendChild(alertLlmRateField);
      configForm.appendChild(alertLlmCallsField);
      configForm.appendChild(alertDetailRateField);
      configForm.appendChild(alertDetailSamplesField);
      configForm.appendChild(alertChannelsField);

      const alertAdvancedPanel = document.createElement("details");
      alertAdvancedPanel.id = "alertAdvancedPanel";
      alertAdvancedPanel.className = "span-2 wizard-panel";
      alertAdvancedPanel.innerHTML = `
        <summary class="wizard-panel-summary">
          <div class="head-row">
            <h4>告警高级配置（双窗口）</h4>
            <span class="wizard-panel-chevron"></span>
          </div>
        </summary>
        <div class="wizard-panel-body">
          <p class="muted">短窗用于识别突发，长窗用于识别趋势。默认参数已可直接使用，非必要不改。</p>
          <div id="alertAdvancedGrid" class="form-grid"></div>
        </div>
      `;
      const alertAdvancedGrid = alertAdvancedPanel.querySelector("#alertAdvancedGrid");
      if (alertAdvancedGrid) {
        [
          alertFetchShortWindowField,
          alertFetchShortMinField,
          alertFetchLongWindowField,
          alertFetchLongThresholdField,
          alertFetchLongMinField,
          alertLlmShortWindowField,
          alertLlmLongWindowField,
          alertLlmLongThresholdField,
          alertLlmLongMinSamplesField,
          alertDetailShortWindowField,
          alertDetailLongWindowField,
          alertDetailLongThresholdField,
          alertDetailLongMinSamplesField,
        ].forEach((field) => alertAdvancedGrid.appendChild(field));
      }
      configForm.appendChild(alertAdvancedPanel);
    }

    const kpis = document.querySelector(".kpis");
    if (kpis && !document.getElementById("performanceSection")) {
      const section = document.createElement("section");
      section.id = "performanceSection";
      section.className = "panel perf-panel enter";
      section.style.setProperty("--delay", "290ms");
      section.innerHTML = `
        <div class="head-row">
          <h3>性能看板</h3>
          <span id="perfSample" class="chip">最近 0 轮</span>
        </div>
        <div class="perf-grid">
          <div class="perf-item"><span>总耗时均值</span><strong id="perfTotalAvg">-</strong></div>
          <div class="perf-item"><span>总耗时 P50</span><strong id="perfTotalP50">-</strong></div>
          <div class="perf-item"><span>总耗时 P95</span><strong id="perfTotalP95">-</strong></div>
          <div class="perf-item"><span>阶段失败率</span><strong id="perfStageFailRate">-</strong></div>
          <div class="perf-item"><span>详情成功率</span><strong id="perfDetailSuccessRate">-</strong></div>
          <div class="perf-item"><span>LLM失败总数</span><strong id="perfLlmFailTotal">-</strong></div>
          <div class="perf-item"><span>抓取失败总数</span><strong id="perfFetchFailTotal">-</strong></div>
          <div class="perf-item"><span>告警触发总数</span><strong id="perfAlertTriggeredTotal">-</strong></div>
          <div class="perf-item"><span>告警已通知总数</span><strong id="perfAlertNotifiedTotal">-</strong></div>
          <div class="perf-item"><span>告警触发轮次占比</span><strong id="perfAlertRunRate">-</strong></div>
        </div>
        <div class="perf-lists">
          <div class="perf-block">
            <h4>慢阶段热点</h4>
            <ul id="perfSlowStages"><li class="table-tip">暂无</li></ul>
          </div>
          <div class="perf-block">
            <h4>错误码分布</h4>
            <ul id="perfErrorCodes"><li class="table-tip">暂无</li></ul>
          </div>
          <div class="perf-block">
            <h4>告警码分布</h4>
            <ul id="perfAlertCodes"><li class="table-tip">暂无</li></ul>
          </div>
        </div>
        <div class="quality-wrap">
          <div class="head-row">
            <h4>质量面板</h4>
            <span class="count">字段完整率与最近趋势</span>
          </div>
          <div class="quality-grid">
            <div class="perf-item"><span>原始线索总数</span><strong id="qualityRawTotal">0</strong></div>
            <div class="perf-item"><span>结构化岗位总数</span><strong id="qualityJobsTotal">0</strong></div>
            <div class="perf-item"><span>正文覆盖率(raw)</span><strong id="qualityDetailFillRate">-</strong></div>
            <div class="perf-item"><span>结构化完整率</span><strong id="qualityStructuredRate">-</strong></div>
            <div class="perf-item"><span>公司字段完整率</span><strong id="qualityCompanyRate">-</strong></div>
            <div class="perf-item"><span>岗位字段完整率</span><strong id="qualityPositionRate">-</strong></div>
            <div class="perf-item"><span>地点字段完整率</span><strong id="qualityLocationRate">-</strong></div>
            <div class="perf-item"><span>要求字段完整率</span><strong id="qualityRequirementsRate">-</strong></div>
            <div class="perf-item"><span>近期提取命中率</span><strong id="qualityExtractionHitRate">-</strong></div>
            <div class="perf-item"><span>近期LLM成功率</span><strong id="qualityLlmSuccessRate">-</strong></div>
            <div class="perf-item"><span>近期详情覆盖率</span><strong id="qualityRecentDetailRate">-</strong></div>
          </div>
          <div class="perf-lists">
            <div class="perf-block">
              <h4>缺失字段 Top</h4>
              <ul id="qualityMissingFields"><li class="table-tip">暂无</li></ul>
            </div>
            <div class="perf-block">
              <h4>最近质量趋势</h4>
              <ul id="qualityTrend"><li class="table-tip">暂无</li></ul>
            </div>
          </div>
        </div>
      `;
      kpis.insertAdjacentElement("afterend", section);
    }

    refreshDynamicDomRefs();
    if (dom.leadStatusFilter) dom.leadStatusFilter.value = state.leadFilters.status;
    if (dom.leadDedupeFilter) dom.leadDedupeFilter.value = state.leadFilters.dedupe;
    if (dom.retryQueueStatusFilter) dom.retryQueueStatusFilter.value = state.retryQueueFilters.status;
    if (dom.retryQueueTypeFilter) dom.retryQueueTypeFilter.value = state.retryQueueFilters.queueType;
  }

  function compactOneLine(value, fallback = "-", maxLen = 120) {
    const text = String(value ?? "")
      .replace(/\s+/g, " ")
      .trim();
    if (!text) return fallback;
    if (text.length <= maxLen) return text;
    return `${text.slice(0, maxLen)}…`;
  }

  function buildLeadDetailHtml(lead, summaryView = isSummaryView()) {
    if (!lead) return defaultDetailHtml();

    const title = toText(lead.title);
    const author = toText(lead.author);
    const publish = toText(lead.publish_time_display || fmtTime(lead.publish_time));
    const company = toText(lead.company);
    const position = toText(lead.position);
    const location = toText(lead.location);
    const req = compactText(lead.requirements, 1200) || "N/A";
    const summary = compactText(lead.summary, 3600) || "N/A";
    const comments = compactText(lead.comments_preview, 1600) || "N/A";
    const detailText = compactText(lead.detail_text, 2600) || "N/A";
    const risk = compactText(lead.risk_flags, 360) || "-";
    const firstSeen = fmtTime(lead.first_seen_at);
    const updatedAt = fmtTime(lead.updated_at);
    const dedupeStatus = String(lead.dedupe_status || "new") === "updated" ? "已更新" : "新增";
    const url = String(lead.url || "").trim();

    if (summaryView) {
      const summaryTitle = `${toText(lead.position, "岗位待补充")} / ${toText(lead.company, "公司待补充")}`;
      return `
        <h4>${escapeHtml(summaryTitle)}</h4>
        <div class="meta-line">发布时间：${escapeHtml(publish)} | 作者：${escapeHtml(author)} | ID：<span class="mono">${escapeHtml(toText(lead.note_id))}</span></div>
        <div class="meta-line">首次发现：${escapeHtml(firstSeen)} | 最近更新：${escapeHtml(updatedAt)} | 增量状态：${escapeHtml(dedupeStatus)}</div>
        <div class="detail-grid">
          <div class="detail-item"><span>公司</span><strong>${escapeHtml(company)}</strong></div>
          <div class="detail-item"><span>岗位</span><strong>${escapeHtml(position)}</strong></div>
          <div class="detail-item"><span>地点</span><strong>${escapeHtml(location)}</strong></div>
          <div class="detail-item"><span>标题</span><strong>${escapeHtml(title)}</strong></div>
        </div>
        <div class="detail-block"><h5>岗位要求</h5><pre>${escapeHtml(req)}</pre></div>
        <div class="detail-block"><h5>摘要</h5><pre>${escapeHtml(summary)}</pre></div>
        ${renderQuickEditBlock(lead)}
        ${url ? `<div class="detail-link"><a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">打开原帖</a></div>` : ""}
      `;
    }

    return `
      <h4>${escapeHtml(title)}</h4>
      <div class="meta-line">作者：${escapeHtml(author)} | 发布时间：${escapeHtml(publish)} | ID：<span class="mono">${escapeHtml(toText(lead.note_id))}</span></div>
      <div class="meta-line">首次发现：${escapeHtml(firstSeen)} | 最近更新：${escapeHtml(updatedAt)} | 增量状态：${escapeHtml(dedupeStatus)}</div>
      <div class="detail-grid">
        <div class="detail-item"><span>公司</span><strong>${escapeHtml(company)}</strong></div>
        <div class="detail-item"><span>岗位</span><strong>${escapeHtml(position)}</strong></div>
        <div class="detail-item"><span>地点</span><strong>${escapeHtml(location)}</strong></div>
        <div class="detail-item"><span>互动</span><strong>赞 ${fmtInt(lead.like_count)} / 评 ${fmtInt(lead.comment_count)} / 分享 ${fmtInt(lead.share_count)}</strong></div>
      </div>
      <div class="detail-block"><h5>岗位要求</h5><pre>${escapeHtml(req)}</pre></div>
      <div class="detail-block"><h5>摘要</h5><pre>${escapeHtml(summary)}</pre></div>
      <div class="detail-block"><h5>贴主评论</h5><pre>${escapeHtml(comments)}</pre></div>
      <div class="detail-block"><h5>原帖正文</h5><pre>${escapeHtml(detailText)}</pre></div>
      <div class="meta-line">风险标记：${escapeHtml(risk)}</div>
      ${renderQuickEditBlock(lead)}
      ${url ? `<div class="detail-link"><a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">打开原帖</a></div>` : ""}
    `;
  }

  function buildRunItemInnerHtml(item) {
    const normalizeSlowStages = (value) => {
      if (!Array.isArray(value)) return [];
      return value
        .filter((entry) => entry && typeof entry === "object")
        .map((entry) => ({
          name: toText(entry.name, "unknown"),
          durationMs: Math.max(0, toInt(entry.duration_ms, 0)),
        }))
        .filter((entry) => entry.durationMs > 0);
    };
    const normalizeErrorCodes = (value) => {
      if (!value || typeof value !== "object") return [];
      return Object.entries(value)
        .map(([code, count]) => ({
          code: String(code || "").trim().toLowerCase(),
          count: Math.max(0, toInt(count, 0)),
        }))
        .filter((entry) => entry.code && entry.count > 0)
        .sort((a, b) => b.count - a.count);
    };

    const runId = toText(item.run_id);
    const t = fmtTime(item.recorded_at);
    const fetched = fmtInt(item.fetched);
    const jobs = fmtInt(item.jobs);
    const sent = fmtInt(item.send_logs);
    const digest = item.digest_sent ? "摘要已发送" : "摘要未发送";
    const digestCls = item.digest_sent ? "ok" : "warn";
    const mode = toText(item.mode);
    const notifyMode = toText(item.notification_mode);
    const stageTotal = fmtMs(item.stage_total_ms);
    const stageAvg = fmtMs(item.stage_avg_ms);
    const stageFailed = Math.max(0, toInt(item.stage_failed_count, 0));
    const alertTriggered = Math.max(0, toInt(item.alerts_triggered_count, 0));
    const slowStages = normalizeSlowStages(item.slow_stages).slice(0, 3);
    const slowStageText = slowStages.length ? slowStages.map((s) => `${s.name} ${fmtMs(s.durationMs)}`).join(" · ") : "暂无";
    const errorCodes = normalizeErrorCodes(item.error_codes);
    const errorHtml = errorCodes.length
      ? errorCodes
          .slice(0, 4)
          .map((entry) => `<span class="run-code">${escapeHtml(entry.code)} × ${fmtInt(entry.count)}</span>`)
          .join("")
      : '<span class="run-code empty">无</span>';
    const remainErrors = errorCodes.length > 4 ? `<span class="run-code">+${errorCodes.length - 4}</span>` : "";

    return `
      <div class="run-head">
        <strong>${escapeHtml(runId)}</strong>
        <span>${escapeHtml(t)}</span>
      </div>
      <div class="run-meta">
        <span>抓取 ${fetched}</span>
        <span>岗位 ${jobs}</span>
        <span>发送 ${sent}</span>
        <span class="run-chip">${escapeHtml(mode)} / ${escapeHtml(notifyMode)}</span>
        <span class="run-chip ${digestCls}">${digest}</span>
        ${alertTriggered > 0 ? `<span class="run-chip warn">告警 ${fmtInt(alertTriggered)}</span>` : ""}
      </div>
      <div class="run-stage">阶段耗时：总计 ${escapeHtml(stageTotal)} · 平均 ${escapeHtml(stageAvg)} · 失败 ${fmtInt(stageFailed)}</div>
      <div class="run-stage">慢阶段：${escapeHtml(slowStageText)}</div>
      <div class="run-codes"><span class="run-label">错误码：</span>${errorHtml}${remainErrors}</div>
    `;
  }

  function buildRunDetailHtml(detail) {
    if (!detail || typeof detail !== "object") {
      return "<p class='muted'>点击一条运行记录后显示详情。</p>";
    }

    const failedStages = Array.isArray(detail.failed_stages) ? detail.failed_stages : [];
    const fetchFails = Array.isArray(detail.fetch_fail_events) ? detail.fetch_fail_events : [];
    const retry = detail.retry && typeof detail.retry === "object" ? detail.retry : {};
    const xhsDiagnosis = detail.xhs_diagnosis && typeof detail.xhs_diagnosis === "object" ? detail.xhs_diagnosis : {};
    const stageErrorCodes = detail.stage_error_codes && typeof detail.stage_error_codes === "object" ? detail.stage_error_codes : {};
    const llmErrorCodes = detail.llm_error_codes && typeof detail.llm_error_codes === "object" ? detail.llm_error_codes : {};
    const alertsTriggered = Array.isArray(detail.alerts_triggered)
      ? detail.alerts_triggered
      : Array.isArray(detail.stats && detail.stats.alerts_triggered)
        ? detail.stats.alerts_triggered
        : [];
    const alertsNotified = Array.isArray(detail.alerts_notified)
      ? detail.alerts_notified
      : Array.isArray(detail.stats && detail.stats.alerts_notified)
        ? detail.stats.alerts_notified
        : [];

    const listCodes = (obj) => {
      const entries = Object.entries(obj || {}).filter(([, v]) => toInt(v, 0) > 0);
      if (!entries.length) return "无";
      return entries
        .slice(0, 8)
        .map(([k, v]) => `${k}: ${fmtInt(v)}`)
        .join(" | ");
    };
    const failedStageHtml = failedStages.length
      ? `<ul class="detail-list">${failedStages
          .slice(0, 8)
          .map((s) => `<li>${escapeHtml(toText(s.name, "unknown"))} · ${escapeHtml(toText(s.error_code, "failed"))}</li>`)
          .join("")}</ul>`
      : "<p class='muted'>无失败阶段。</p>";

    const fetchFailHtml = fetchFails.length
      ? `<ul class="detail-list">${fetchFails
          .slice(0, 8)
          .map((s) => `<li>${escapeHtml(toText(s.stage, "-"))}: ${escapeHtml(toText(s.error, "-"))}</li>`)
          .join("")}</ul>`
      : "<p class='muted'>无抓取失败事件。</p>";

    const retryPending = retry.pending && typeof retry.pending === "object" ? retry.pending : {};
    const retryRunning = retry.running && typeof retry.running === "object" ? retry.running : {};
    const retryStats = retry.stats && typeof retry.stats === "object" ? retry.stats : {};
    const alertListHtml = alertsTriggered.length
      ? `<ul class="detail-list">${alertsTriggered
          .slice(0, 8)
          .map((item) => {
            const code = toText(item && item.code, "unknown");
            const reason = toText(item && item.reason, "-");
            const value = item && item.value !== undefined ? String(item.value) : "-";
            const threshold = item && item.threshold !== undefined ? String(item.threshold) : "-";
            return `<li>${escapeHtml(code)} | value=${escapeHtml(value)} | threshold=${escapeHtml(threshold)} | ${escapeHtml(reason)}</li>`;
          })
          .join("")}</ul>`
      : "<p class='muted'>未触发阈值告警。</p>";
    const alertNotifiedText = alertsNotified.length ? alertsNotified.map((item) => String(item)).join(" | ") : "无";

    return `
      <div class="meta-line">Run：<span class="mono">${escapeHtml(toText(detail.run_id))}</span> · ${escapeHtml(fmtTime(detail.recorded_at))}</div>
      <div class="detail-grid">
        <div class="detail-item"><span>失败阶段数</span><strong>${fmtInt(failedStages.length)}</strong></div>
        <div class="detail-item"><span>抓取失败数</span><strong>${fmtInt(fetchFails.length)}</strong></div>
        <div class="detail-item"><span>重试待执行</span><strong>${fmtInt(Object.values(retryPending).reduce((a, b) => a + toInt(b, 0), 0))}</strong></div>
        <div class="detail-item"><span>重试执行中</span><strong>${fmtInt(Object.values(retryRunning).reduce((a, b) => a + toInt(b, 0), 0))}</strong></div>
      </div>
      <div class="detail-block"><h5>阈值告警</h5>${alertListHtml}</div>
      <div class="detail-block"><h5>已通知告警码</h5><pre>${escapeHtml(alertNotifiedText)}</pre></div>
      <div class="detail-block"><h5>失败阶段</h5>${failedStageHtml}</div>
      <div class="detail-block"><h5>抓取失败事件</h5>${fetchFailHtml}</div>
      <div class="detail-block"><h5>阶段错误码</h5><pre>${escapeHtml(listCodes(stageErrorCodes))}</pre></div>
      <div class="detail-block"><h5>LLM 错误码</h5><pre>${escapeHtml(listCodes(llmErrorCodes))}</pre></div>
      <div class="detail-block"><h5>XHS 诊断</h5><pre>${escapeHtml(JSON.stringify(xhsDiagnosis, null, 2) || "{}")}</pre></div>
      <div class="detail-block"><h5>重试快照</h5><pre>${escapeHtml(JSON.stringify({ pending: retryPending, running: retryRunning, stats: retryStats }, null, 2))}</pre></div>
    `;
  }

  function ensureWorkspaceVue() {
    if (workspaceVue || !dom.workspace || !window.Vue || !window.Vue.createApp) return workspaceVue;
    const { createApp } = window.Vue;

    workspaceVueApp = createApp({
      data() {
        return {
          view: state.view,
          leads: [],
          selectedNoteId: "",
          tableLoading: "",
          tableError: "",
          pagination: { ...state.pagination },
          runItems: [],
          selectedRunId: "",
          runDetailHtml: "<p class='muted'>点击一条运行记录后显示详情。</p>",
        };
      },
      computed: {
        summaryView() {
          return this.view === "summary";
        },
        tableColspan() {
          return this.summaryView ? 4 : 5;
        },
        leadCountText() {
          return `${fmtInt(this.leads.length)} 条`;
        },
        pageCurrent() {
          return toInt(this.pagination.page, 1);
        },
        pageTotal() {
          return Math.max(1, toInt(this.pagination.totalPages, 1));
        },
        pageSizeText() {
          return String(toInt(this.pagination.pageSize, 30));
        },
        prevDisabled() {
          return this.pageCurrent <= 1;
        },
        nextDisabled() {
          return this.pageCurrent >= this.pageTotal;
        },
        pageInfoText() {
          const page = this.pageCurrent;
          const totalPages = this.pageTotal;
          const total = toInt(this.pagination.total, 0);
          return `${page} / ${totalPages} · 共 ${fmtInt(total)} 条`;
        },
        selectedLead() {
          if (!this.leads.length) return null;
          const hit = this.leads.find((x) => x.note_id === this.selectedNoteId);
          return hit || this.leads[0];
        },
        detailHtml() {
          return buildLeadDetailHtml(this.selectedLead, this.summaryView);
        },
      },
      methods: {
        selectLead(noteId) {
          const value = String(noteId || "").trim();
          if (!value) return;
          this.selectedNoteId = value;
          state.selectedNoteId = value;
        },
        selectRun(runId) {
          const value = String(runId || "").trim();
          if (!value) return;
          this.selectedRunId = value;
          state.selectedRunId = value;
          this.runDetailHtml = "<p class='muted'>正在加载运行详情...</p>";
          if (typeof window.__spLoadRunDetail === "function") {
            window.__spLoadRunDetail(value);
          }
        },
        rowClass(noteId) {
          return String(noteId || "").trim() === String(this.selectedNoteId || "").trim() ? "active" : "";
        },
        publishText(lead) {
          return toText(lead.publish_time_display || fmtTime(lead.publish_time));
        },
        text(value, fallback = "-") {
          return toText(value, fallback);
        },
        jobLine(lead) {
          return `${toText(lead.position, "岗位待补充")} / ${toText(lead.company, "公司待补充")}`;
        },
        requirementLine(lead) {
          return compactOneLine(lead.requirements, "岗位要求待补充", 90);
        },
        summaryLine(lead) {
          return compactOneLine(lead.summary, "暂无摘要", 130);
        },
        dedupeText(lead) {
          return String(lead.dedupe_status || "new") === "updated" ? "已更新" : "新增";
        },
        interactText(lead) {
          return `赞 ${fmtInt(lead.like_count)} / 评 ${fmtInt(lead.comment_count)}`;
        },
        updateLine(lead) {
          return `更新 ${fmtTime(lead.updated_at)} · ${this.dedupeText(lead)}`;
        },
        statusBadgeHtml(lead) {
          return statusBadge(lead.status, lead.like_count, lead.comment_count);
        },
        runItemInnerHtml(item) {
          return buildRunItemInnerHtml(item);
        },
        applyLeads(items, pagination) {
          this.tableLoading = "";
          this.tableError = "";
          this.leads = Array.isArray(items) ? items : [];
          this.pagination = {
            page: toInt(pagination.page, 1),
            pageSize: toInt(pagination.pageSize, pageSizeForView(this.view)),
            total: toInt(pagination.total, 0),
            totalPages: Math.max(1, toInt(pagination.totalPages, 1)),
          };
          if (!this.leads.length) {
            this.selectedNoteId = "";
            state.selectedNoteId = "";
            return;
          }
          if (!this.selectedNoteId || !this.leads.some((x) => x.note_id === this.selectedNoteId)) {
            this.selectedNoteId = this.leads[0].note_id;
          }
          state.selectedNoteId = this.selectedNoteId;
        },
        setLoading(message) {
          this.tableError = "";
          this.tableLoading = String(message || "加载中...");
          this.leads = [];
        },
        setError(message) {
          this.tableLoading = "";
          this.tableError = String(message || "加载失败");
          this.leads = [];
        },
        applyRuns(items) {
            this.runItems = Array.isArray(items) ? items : [];
            if (!this.runItems.length) {
              this.selectedRunId = "";
              state.selectedRunId = "";
              this.runDetailHtml = "<p class='muted'>暂无运行记录。</p>";
              return;
            }
          const hasSelected = this.runItems.some((item) => item && item.run_id === this.selectedRunId);
          if (!this.selectedRunId || !hasSelected) {
            this.selectedRunId = String(this.runItems[0].run_id || "");
          }
          state.selectedRunId = this.selectedRunId;
        },
        applyRunDetail(detail) {
          this.runDetailHtml = buildRunDetailHtml(detail);
        },
      },
      template: `
        <article class="panel table-panel enter" style="--delay: 320ms">
          <div class="head-row">
            <h3>{{ summaryView ? '摘要列表' : '线索列表' }}</h3>
            <span class="count" id="leadCount">{{ leadCountText }}</span>
            <div id="leadFiltersRow" class="lead-filters-row">
              <label class="mini-field">
                <span>状态</span>
                <select id="leadStatusFilter">
                  <option value="all">全部</option>
                  <option value="high_priority">高优先级</option>
                  <option value="actionable">可推进</option>
                  <option value="pending_review">待复核</option>
                  <option value="new_lead">新线索</option>
                </select>
              </label>
              <label class="mini-field">
                <span>去重状态</span>
                <select id="leadDedupeFilter">
                  <option value="all">全部</option>
                  <option value="new">新增</option>
                  <option value="updated">已更新</option>
                </select>
              </label>
            </div>
          </div>
          <div class="pager" id="leadPager">
            <button id="leadPrevBtn" class="btn ghost" type="button" :disabled="prevDisabled">上一页</button>
            <span id="leadPageInfo">{{ pageInfoText }}</span>
            <button id="leadNextBtn" class="btn ghost" type="button" :disabled="nextDisabled">下一页</button>
            <label class="pager-size">
              <span>每页</span>
              <select id="leadPageSize" :value="pageSizeText">
                <option value="10">10</option>
                <option value="20">20</option>
                <option value="30">30</option>
                <option value="50">50</option>
              </select>
            </label>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr v-if="summaryView">
                  <th>发布时间</th>
                  <th>岗位 / 公司</th>
                  <th>岗位要求</th>
                  <th>摘要</th>
                </tr>
                <tr v-else>
                  <th>发布时间</th>
                  <th>岗位 / 公司</th>
                  <th>地点</th>
                  <th>互动</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody id="leadBody">
                <tr v-if="tableLoading"><td :colspan="tableColspan" class="table-tip">{{ tableLoading }}</td></tr>
                <tr v-else-if="tableError"><td :colspan="tableColspan" class="table-tip error">{{ tableError }}</td></tr>
                <tr v-else-if="!leads.length"><td :colspan="tableColspan" class="table-tip">暂无匹配线索</td></tr>
                <template v-else>
                  <tr
                    v-for="lead in leads"
                    :key="lead.note_id"
                    :class="rowClass(lead.note_id)"
                    :data-id="lead.note_id"
                    tabindex="0"
                    role="button"
                    @click="selectLead(lead.note_id)"
                    @keydown.enter.prevent="selectLead(lead.note_id)"
                    @keydown.space.prevent="selectLead(lead.note_id)"
                  >
                    <td>{{ publishText(lead) }}</td>
                    <td>
                      <div class="title-cell">{{ jobLine(lead) }}</div>
                      <div class="sub-cell" v-if="summaryView">{{ text(lead.location) }} · {{ dedupeText(lead) }}</div>
                      <template v-else>
                        <div class="sub-cell">{{ text(lead.title) }}</div>
                        <div class="sub-cell">{{ updateLine(lead) }}</div>
                      </template>
                    </td>
                    <td v-if="summaryView">{{ requirementLine(lead) }}</td>
                    <td v-if="summaryView">{{ summaryLine(lead) }}</td>
                    <td v-if="!summaryView">{{ text(lead.location) }}</td>
                    <td v-if="!summaryView">{{ interactText(lead) }}</td>
                    <td v-if="!summaryView" v-html="statusBadgeHtml(lead)"></td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </article>

        <article class="panel detail-panel enter" style="--delay: 370ms">
          <div class="head-row">
            <h3>{{ summaryView ? '摘要详情' : '线索详情' }}</h3>
            <span class="chip">{{ summaryView ? '结构化视图' : '实时数据' }}</span>
          </div>
          <div id="detailBox" class="detail-box" v-html="detailHtml"></div>
          <div class="runs-box">
            <h4>运行记录</h4>
            <ul id="runList">
              <li v-if="!runItems.length">暂无运行记录</li>
              <li
                v-for="item in runItems"
                :key="String(item.run_id || '')"
                class="run-item"
                :class="{ active: String(item.run_id || '') === String(selectedRunId || '') }"
                :data-run-id="String(item.run_id || '')"
                tabindex="0"
                role="button"
                @click="selectRun(item.run_id)"
                @keydown.enter.prevent="selectRun(item.run_id)"
                @keydown.space.prevent="selectRun(item.run_id)"
                v-html="runItemInnerHtml(item)"
              ></li>
            </ul>
            <div id="runDetailBox" class="run-detail-box" v-html="runDetailHtml"></div>
          </div>
        </article>
      `,
    });

    workspaceVue = workspaceVueApp.mount(dom.workspace);

    dom.leadCount = document.getElementById("leadCount");
    dom.leadBody = document.getElementById("leadBody");
    dom.detailBox = document.getElementById("detailBox");
    dom.runList = document.getElementById("runList");
    dom.runDetailBox = document.getElementById("runDetailBox");
    dom.leadPageInfo = document.getElementById("leadPageInfo");
    dom.leadPrevBtn = document.getElementById("leadPrevBtn");
    dom.leadNextBtn = document.getElementById("leadNextBtn");
    dom.leadPageSize = document.getElementById("leadPageSize");
    dom.leadPager = document.getElementById("leadPager");
    dom.leadStatusFilter = document.getElementById("leadStatusFilter");
    dom.leadDedupeFilter = document.getElementById("leadDedupeFilter");
    return workspaceVue;
  }

  function renderWorkspaceLayout() {
    const vm = ensureWorkspaceVue();
    if (vm) {
      vm.view = state.view;
    }
  }

  function renderSummary(summary) {
    if (dom.kpiRaw) dom.kpiRaw.textContent = fmtInt(summary.raw_count);
    if (dom.kpiSummary) dom.kpiSummary.textContent = fmtInt(summary.summary_count);
    if (dom.kpiJobs) dom.kpiJobs.textContent = fmtInt(summary.jobs_count);
    if (dom.kpiSend) dom.kpiSend.textContent = fmtInt(summary.send_count);

    if (dom.latestRunId) dom.latestRunId.textContent = toText(summary.latest_run_id);
    if (dom.latestRunTime) dom.latestRunTime.textContent = fmtTime(summary.latest_run_time);
    if (dom.digestMinutes) dom.digestMinutes.textContent = fmtInt(summary.digest_interval_minutes || 60);
  }

  function formatRate(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "-";
    return `${(n * 100).toFixed(1)}%`;
  }

  function buildPerformanceFromRuns(items) {
    const runs = Array.isArray(items) ? items : [];
    const totals = runs.map((item) => toInt(item.stage_total_ms, 0)).filter((x) => x > 0).sort((a, b) => a - b);
    const sampleSize = runs.length;
    const pickPercentile = (arr, q) => {
      if (!arr.length) return 0;
      if (arr.length === 1) return arr[0];
      const pos = (arr.length - 1) * q;
      const lo = Math.floor(pos);
      const hi = Math.min(arr.length - 1, lo + 1);
      const w = pos - lo;
      return Math.round(arr[lo] + (arr[hi] - arr[lo]) * w);
    };
    const stageFailedRuns = runs.filter((item) => toInt(item.stage_failed_count, 0) > 0).length;
    const llmFailTotal = runs.reduce((sum, item) => sum + toInt(item.llm_fail, 0), 0);
    const fetchFailTotal = runs.reduce((sum, item) => sum + toInt(item.fetch_fail_count_run, 0), 0);
    const detailAttemptedTotal = runs.reduce((sum, item) => sum + toInt(item.detail_attempted, 0), 0);
    const detailSuccessTotal = runs.reduce((sum, item) => sum + toInt(item.detail_success, 0), 0);
    const alertTriggeredTotal = runs.reduce((sum, item) => sum + toInt(item.alerts_triggered_count, 0), 0);
    const alertNotifiedTotal = runs.reduce((sum, item) => sum + toInt(item.alerts_notified_count, 0), 0);
    const alertTriggeredRuns = runs.filter((item) => toInt(item.alerts_triggered_count, 0) > 0).length;

    const errorAgg = {};
    const alertAgg = {};
    const slowAgg = {};
    runs.forEach((item) => {
      const codes = item.error_codes && typeof item.error_codes === "object" ? item.error_codes : {};
      Object.entries(codes).forEach(([code, count]) => {
        const key = String(code || "").trim().toLowerCase();
        if (!key) return;
        errorAgg[key] = toInt(errorAgg[key], 0) + toInt(count, 0);
      });
      const alertCodes = Array.isArray(item.alert_codes)
        ? item.alert_codes
        : Array.isArray(item.alerts_triggered)
          ? item.alerts_triggered.map((entry) => (entry && typeof entry === "object" ? entry.code : ""))
          : [];
      alertCodes.forEach((code) => {
        const key = String(code || "").trim().toLowerCase();
        if (!key) return;
        alertAgg[key] = toInt(alertAgg[key], 0) + 1;
      });
      const slowStages = Array.isArray(item.slow_stages) ? item.slow_stages : [];
      slowStages.forEach((stage) => {
        if (!stage || typeof stage !== "object") return;
        const name = toText(stage.name, "unknown");
        const duration = toInt(stage.duration_ms, 0);
        const bucket = slowAgg[name] || { name, count: 0, max_ms: 0 };
        bucket.count += 1;
        bucket.max_ms = Math.max(bucket.max_ms, duration);
        slowAgg[name] = bucket;
      });
    });

    const errorCodes = Object.entries(errorAgg)
      .map(([code, count]) => ({ code, count: toInt(count, 0) }))
      .filter((x) => x.count > 0)
      .sort((a, b) => b.count - a.count);
    const alertCodes = Object.entries(alertAgg)
      .map(([code, count]) => ({ code, count: toInt(count, 0) }))
      .filter((x) => x.count > 0)
      .sort((a, b) => b.count - a.count);
    const slowStages = Object.values(slowAgg)
      .sort((a, b) => (b.count - a.count) || (b.max_ms - a.max_ms))
      .slice(0, 10);
    const llmCallsTotal = runs.reduce((sum, item) => sum + toInt(item.llm_calls, 0), 0);
    const llmSuccessTotal = runs.reduce((sum, item) => sum + toInt(item.llm_success, 0), 0);
    const detailTargetTotal = runs.reduce((sum, item) => sum + toInt(item.detail_target_notes, 0), 0);
    const detailMissingTotal = runs.reduce((sum, item) => sum + toInt(item.detail_missing, 0), 0);
    const targetTotal = runs.reduce((sum, item) => sum + toInt(item.target_notes, 0), 0);
    const jobsTotalRecent = runs.reduce((sum, item) => sum + toInt(item.jobs, 0), 0);
    const trend = runs.slice(0, 12).map((item) => {
      const target = toInt(item.target_notes, 0);
      const jobs = toInt(item.jobs, 0);
      const llmCalls = toInt(item.llm_calls, 0);
      const llmSuccess = toInt(item.llm_success, 0);
      const detailTarget = toInt(item.detail_target_notes, 0);
      const detailMissing = toInt(item.detail_missing, 0);
      return {
        run_id: toText(item.run_id, ""),
        recorded_at: toText(item.recorded_at, ""),
        extraction_hit_rate: target > 0 ? jobs / target : 0,
        llm_success_rate: llmCalls > 0 ? llmSuccess / llmCalls : 0,
        detail_fill_rate: detailTarget > 0 ? Math.max(0, detailTarget - detailMissing) / detailTarget : 0,
      };
    });

    return {
      sample_size: sampleSize,
      stage_total_ms: {
        avg: totals.length ? Math.round(totals.reduce((a, b) => a + b, 0) / totals.length) : 0,
        p50: pickPercentile(totals, 0.5),
        p95: pickPercentile(totals, 0.95),
      },
      stage_failed_runs: stageFailedRuns,
      stage_failed_rate: sampleSize > 0 ? stageFailedRuns / sampleSize : 0,
      detail_success_rate: detailAttemptedTotal > 0 ? detailSuccessTotal / detailAttemptedTotal : 0,
      llm_fail_total: llmFailTotal,
      fetch_fail_total: fetchFailTotal,
      alert_triggered_total: alertTriggeredTotal,
      alert_notified_total: alertNotifiedTotal,
      alert_triggered_runs: alertTriggeredRuns,
      alert_triggered_rate: sampleSize > 0 ? alertTriggeredRuns / sampleSize : 0,
      error_codes: errorCodes,
      alert_codes: alertCodes,
      slow_stages: slowStages,
      quality: {
        raw_total: 0,
        jobs_total: 0,
        detail_fill_rate: 0,
        structured_complete_rate: 0,
        company_fill_rate: 0,
        position_fill_rate: 0,
        location_fill_rate: 0,
        requirements_fill_rate: 0,
        recent_extraction_hit_rate: targetTotal > 0 ? jobsTotalRecent / targetTotal : 0,
        recent_llm_success_rate: llmCallsTotal > 0 ? llmSuccessTotal / llmCallsTotal : 0,
        recent_detail_fill_rate: detailTargetTotal > 0 ? Math.max(0, detailTargetTotal - detailMissingTotal) / detailTargetTotal : 0,
        missing_fields_top: [],
        trend,
      },
    };
  }

  function renderPerformance(payload) {
    if (!dom.perfSample) return;
    const data = payload && typeof payload === "object" ? payload : {};
    const total = data.stage_total_ms && typeof data.stage_total_ms === "object" ? data.stage_total_ms : {};
    const sample = toInt(data.sample_size, 0);
    const stageFailedRate = Number(data.stage_failed_rate || 0);
    const detailSuccessRate = Number(data.detail_success_rate || 0);
    const llmFailTotal = toInt(data.llm_fail_total, 0);
    const fetchFailTotal = toInt(data.fetch_fail_total, 0);
    const alertTriggeredTotal = toInt(data.alert_triggered_total, 0);
    const alertNotifiedTotal = toInt(data.alert_notified_total, 0);
    const alertTriggeredRate = Number(data.alert_triggered_rate || 0);
    const slowStages = Array.isArray(data.slow_stages) ? data.slow_stages : [];
    const errorCodes = Array.isArray(data.error_codes) ? data.error_codes : [];
    const alertCodes = Array.isArray(data.alert_codes) ? data.alert_codes : [];
    const quality = data.quality && typeof data.quality === "object" ? data.quality : {};
    const missingFieldsTop = Array.isArray(quality.missing_fields_top) ? quality.missing_fields_top : [];
    const qualityTrend = Array.isArray(quality.trend) ? quality.trend : [];

    dom.perfSample.textContent = `最近 ${fmtInt(sample)} 轮`;
    if (dom.perfTotalAvg) dom.perfTotalAvg.textContent = fmtMs(total.avg);
    if (dom.perfTotalP50) dom.perfTotalP50.textContent = fmtMs(total.p50);
    if (dom.perfTotalP95) dom.perfTotalP95.textContent = fmtMs(total.p95);
    if (dom.perfStageFailRate) dom.perfStageFailRate.textContent = formatRate(stageFailedRate);
    if (dom.perfDetailSuccessRate) dom.perfDetailSuccessRate.textContent = formatRate(detailSuccessRate);
    if (dom.perfLlmFailTotal) dom.perfLlmFailTotal.textContent = fmtInt(llmFailTotal);
    if (dom.perfFetchFailTotal) dom.perfFetchFailTotal.textContent = fmtInt(fetchFailTotal);
    if (dom.perfAlertTriggeredTotal) dom.perfAlertTriggeredTotal.textContent = fmtInt(alertTriggeredTotal);
    if (dom.perfAlertNotifiedTotal) dom.perfAlertNotifiedTotal.textContent = fmtInt(alertNotifiedTotal);
    if (dom.perfAlertRunRate) dom.perfAlertRunRate.textContent = formatRate(alertTriggeredRate);
    if (dom.qualityRawTotal) dom.qualityRawTotal.textContent = fmtInt(toInt(quality.raw_total, 0));
    if (dom.qualityJobsTotal) dom.qualityJobsTotal.textContent = fmtInt(toInt(quality.jobs_total, 0));
    if (dom.qualityDetailFillRate) dom.qualityDetailFillRate.textContent = formatRate(Number(quality.detail_fill_rate || 0));
    if (dom.qualityStructuredRate) dom.qualityStructuredRate.textContent = formatRate(Number(quality.structured_complete_rate || 0));
    if (dom.qualityCompanyRate) dom.qualityCompanyRate.textContent = formatRate(Number(quality.company_fill_rate || 0));
    if (dom.qualityPositionRate) dom.qualityPositionRate.textContent = formatRate(Number(quality.position_fill_rate || 0));
    if (dom.qualityLocationRate) dom.qualityLocationRate.textContent = formatRate(Number(quality.location_fill_rate || 0));
    if (dom.qualityRequirementsRate) dom.qualityRequirementsRate.textContent = formatRate(Number(quality.requirements_fill_rate || 0));
    if (dom.qualityExtractionHitRate) dom.qualityExtractionHitRate.textContent = formatRate(Number(quality.recent_extraction_hit_rate || 0));
    if (dom.qualityLlmSuccessRate) dom.qualityLlmSuccessRate.textContent = formatRate(Number(quality.recent_llm_success_rate || 0));
    if (dom.qualityRecentDetailRate) dom.qualityRecentDetailRate.textContent = formatRate(Number(quality.recent_detail_fill_rate || 0));

    if (dom.perfSlowStages) {
      if (!slowStages.length) {
        dom.perfSlowStages.innerHTML = "<li class='table-tip'>暂无</li>";
      } else {
        dom.perfSlowStages.innerHTML = slowStages
          .slice(0, 6)
          .map((stage) => {
            const name = toText(stage.name, "unknown");
            const count = fmtInt(stage.count);
            const p95 = fmtMs(stage.p95_ms || stage.max_ms || 0);
            return `<li><span>${escapeHtml(name)}</span><span>${count} 次 · ${escapeHtml(p95)}</span></li>`;
          })
          .join("");
      }
    }

    if (dom.perfErrorCodes) {
      if (!errorCodes.length) {
        dom.perfErrorCodes.innerHTML = "<li class='table-tip'>暂无</li>";
      } else {
        dom.perfErrorCodes.innerHTML = errorCodes
          .slice(0, 6)
          .map((item) => `<li><span>${escapeHtml(toText(item.code))}</span><span>${fmtInt(item.count)}</span></li>`)
          .join("");
      }
    }
    if (dom.perfAlertCodes) {
      if (!alertCodes.length) {
        dom.perfAlertCodes.innerHTML = "<li class='table-tip'>暂无</li>";
      } else {
        dom.perfAlertCodes.innerHTML = alertCodes
          .slice(0, 6)
          .map((item) => `<li><span>${escapeHtml(toText(item.code))}</span><span>${fmtInt(item.count)}</span></li>`)
          .join("");
      }
    }
    if (dom.qualityMissingFields) {
      if (!missingFieldsTop.length) {
        dom.qualityMissingFields.innerHTML = "<li class='table-tip'>暂无</li>";
      } else {
        dom.qualityMissingFields.innerHTML = missingFieldsTop
          .slice(0, 6)
          .map((item) => `<li><span>${escapeHtml(toText(item.field))}</span><span>${fmtInt(item.missing)}</span></li>`)
          .join("");
      }
    }
    if (dom.qualityTrend) {
      if (!qualityTrend.length) {
        dom.qualityTrend.innerHTML = "<li class='table-tip'>暂无</li>";
      } else {
        dom.qualityTrend.innerHTML = qualityTrend
          .slice(0, 8)
          .map((item) => {
            const runText = toText(item.run_id, "-");
            const hitRate = formatRate(Number(item.extraction_hit_rate || 0));
            const detailRate = formatRate(Number(item.detail_fill_rate || 0));
            const llmRate = formatRate(Number(item.llm_success_rate || 0));
            return `<li><span>${escapeHtml(runText)}</span><span>命中 ${hitRate} · 详情 ${detailRate} · LLM ${llmRate}</span></li>`;
          })
          .join("");
      }
    }
  }

  function renderRuns(items) {
    state.runItems = Array.isArray(items) ? items : [];
    if (!workspaceVue || typeof workspaceVue.applyRuns !== 'function') return;
    workspaceVue.applyRuns(state.runItems);
  }

  function renderRunDetail(detail) {
    state.runDetail = detail || null;
    if (!workspaceVue || typeof workspaceVue.applyRunDetail !== 'function') return;
    workspaceVue.applyRunDetail(state.runDetail);
  }

  async function loadRunDetail(runId) {
    const id = String(runId || "").trim();
    if (!id) {
      renderRunDetail(null);
      return;
    }
    if (workspaceVue && typeof workspaceVue.applyRunDetail === "function") {
      workspaceVue.applyRunDetail({ run_id: id, recorded_at: "", failed_stages: [], fetch_fail_events: [] });
    } else if (dom.runDetailBox) {
      dom.runDetailBox.innerHTML = "<p class='muted'>正在加载运行详情...</p>";
    }
    const detail = await fetchJson(`/api/runs/${encodeURIComponent(id)}`);
    renderRunDetail(detail || null);
  }

  function renderPagination() {
    if (!workspaceVue) return;
    workspaceVue.pagination = {
      page: toInt(state.pagination.page, 1),
      pageSize: toInt(state.pagination.pageSize, pageSizeForView(state.view)),
      total: toInt(state.pagination.total, 0),
      totalPages: Math.max(1, toInt(state.pagination.totalPages, 1)),
    };
  }

  function getSelectedLead() {
    const currentSelected = workspaceVue ? String(workspaceVue.selectedNoteId || state.selectedNoteId || "") : state.selectedNoteId;
    if (!state.leads.length) return null;
    const byId = state.leads.find((x) => x.note_id === currentSelected);
    if (byId) return byId;
    state.selectedNoteId = state.leads[0].note_id;
    if (workspaceVue) workspaceVue.selectedNoteId = state.selectedNoteId;
    return state.leads[0];
  }

  function compactText(value, limit = 2200) {
    const text = String(value ?? "").trim();
    if (!text) return "";
    if (text.length <= limit) return text;
    return `${text.slice(0, limit)}\n...（界面展示已截断，共 ${text.length} 字）`;
  }



  function normalizeEditableText(value) {
    return String(value ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim();
  }

  function hasUnsavedQuickEditChanges() {
    if (!isWorkspaceView(state.view) || !dom.detailBox) return false;
    const form = dom.detailBox.querySelector("form.quick-edit-form");
    if (!form) return false;
    const selected = getSelectedLead();
    if (!selected) return false;
    const formData = new FormData(form);
    for (const key of QUICK_EDIT_FIELDS) {
      const currentValue = normalizeEditableText(formData.get(key));
      const selectedValue = normalizeEditableText(selected[key]);
      if (currentValue !== selectedValue) {
        return true;
      }
    }
    return false;
  }

  function renderQuickEditBlock(lead) {
    const noteId = String(lead.note_id || "").trim();
    if (!noteId) return "";
    const title = normalizeEditableText(lead.title);
    const position = normalizeEditableText(lead.position);
    const company = normalizeEditableText(lead.company);
    const location = normalizeEditableText(lead.location);
    const requirements = normalizeEditableText(lead.requirements);
    const summary = normalizeEditableText(lead.summary);
    return `
      <div class="detail-block quick-edit-block">
        <h5>快速改字段</h5>
        <form class="quick-edit-form" data-note-id="${escapeHtml(noteId)}">
          <div class="quick-edit-grid">
            <label class="quick-edit-field">
              <span>标题</span>
              <input name="title" type="text" value="${escapeHtml(title)}" />
            </label>
            <label class="quick-edit-field">
              <span>岗位</span>
              <input name="position" type="text" value="${escapeHtml(position)}" />
            </label>
            <label class="quick-edit-field">
              <span>公司</span>
              <input name="company" type="text" value="${escapeHtml(company)}" />
            </label>
          </div>
          <label class="quick-edit-field">
            <span>地点</span>
            <input name="location" type="text" value="${escapeHtml(location)}" />
          </label>
          <label class="quick-edit-field">
            <span>岗位要求</span>
            <textarea name="requirements" rows="4">${escapeHtml(requirements)}</textarea>
          </label>
          <label class="quick-edit-field">
            <span>摘要</span>
            <textarea name="summary" rows="5">${escapeHtml(summary)}</textarea>
          </label>
          <div class="quick-edit-actions">
            <button class="btn primary" type="submit" data-role="lead-edit-save">保存字段</button>
            <span class="quick-edit-tip">回写本地表格（output.xlsx）并立即刷新当前列表</span>
          </div>
        </form>
      </div>
    `;
  }

  function renderDetail(lead) {
    const noteId = lead && lead.note_id ? String(lead.note_id) : "";
    state.selectedNoteId = noteId;
    if (workspaceVue) {
      workspaceVue.selectedNoteId = noteId;
      return;
    }
    if (!dom.detailBox) return;
    dom.detailBox.innerHTML = buildLeadDetailHtml(lead, isSummaryView());
  }

  function renderLeads(items) {
    state.leads = Array.isArray(items) ? items : [];
    if (dom.leadCount) dom.leadCount.textContent = fmtInt(state.leads.length) + ' 条';
    if (!workspaceVue || typeof workspaceVue.applyLeads !== 'function') return;
    workspaceVue.applyLeads(state.leads, state.pagination);
  }

  function setLoadingTable(message = "加载中...") {
    if (workspaceVue && typeof workspaceVue.setLoading === "function") {
      workspaceVue.setLoading(message);
      return;
    }
    if (!dom.leadBody) return;
    dom.leadBody.innerHTML = `<tr><td colspan="${tableColumnCount()}" class="table-tip">${escapeHtml(message)}</td></tr>`;
  }

  function setTableError(message) {
    if (workspaceVue && typeof workspaceVue.setError === "function") {
      workspaceVue.setError(message);
      return;
    }
    if (!dom.leadBody) return;
    dom.leadBody.innerHTML = `<tr><td colspan="${tableColumnCount()}" class="table-tip error">${escapeHtml(message)}</td></tr>`;
  }

  function extractProgressFromLogs(logs) {
    if (!Array.isArray(logs)) return null;
    const re = /\[\s*[#\-]{6,}\s*\]\s*(\d{1,3})%\s*\|\s*(.+)$/;
    for (let i = logs.length - 1; i >= 0; i -= 1) {
      const line = String(logs[i] || "").trim();
      if (!line) continue;
      const match = line.match(re);
      if (!match) continue;
      return {
        percent: Math.max(0, Math.min(100, toInt(match[1], 0))),
        message: String(match[2] || "").trim(),
      };
    }
    return null;
  }

  function renderRuntime(runtime) {
    state.runtime = runtime || {};
    const daemon = (runtime && runtime.daemon) || {};
    const job = (runtime && runtime.job) || {};
    const updated = (runtime && runtime.updated_at) || "";
    const daemonRunning = Boolean(daemon.running);
    const jobRunning = Boolean(job.running);

    if (dom.daemonQuickState) dom.daemonQuickState.textContent = daemonRunning ? "运行中" : "已停止";
    if (dom.jobQuickState) dom.jobQuickState.textContent = jobRunning ? `执行中(${toText(job.name, "任务")})` : "空闲";
    if (dom.daemonStateText) dom.daemonStateText.textContent = daemonRunning ? "运行中" : "已停止";
    if (dom.runtimeDaemonState) dom.runtimeDaemonState.textContent = daemonRunning ? `运行中 PID:${toText(daemon.pid)}` : "已停止";
    if (dom.runtimeJobState) dom.runtimeJobState.textContent = jobRunning ? `执行中: ${toText(job.name)}` : `空闲: ${toText(job.message, "-")}`;
    if (dom.runtimeUpdatedAt) dom.runtimeUpdatedAt.textContent = fmtTime(updated);

    let logs = [];
    if (jobRunning || (Array.isArray(job.log_tail) && job.log_tail.length)) {
      logs = Array.isArray(job.log_tail) ? job.log_tail : [];
    } else if (Array.isArray(daemon.log_tail) && daemon.log_tail.length) {
      logs = daemon.log_tail;
    }
    if (dom.runtimeLog) dom.runtimeLog.textContent = logs.length ? logs.join("\n") : "暂无运行输出";

    const progress = (job && job.progress && typeof job.progress === "object" ? job.progress : null) || extractProgressFromLogs(logs);
    if (dom.runtimeProgressWrap && dom.runtimeProgressBar && dom.runtimeProgressText) {
      if (progress && typeof progress.percent === "number") {
        const pct = Math.max(0, Math.min(100, toInt(progress.percent, 0)));
        dom.runtimeProgressWrap.classList.remove("hidden");
        dom.runtimeProgressBar.style.width = `${pct}%`;
        dom.runtimeProgressText.textContent = `${pct}% · ${toText(progress.message, "处理中")}`;
      } else {
        dom.runtimeProgressWrap.classList.add("hidden");
        dom.runtimeProgressBar.style.width = "0%";
        dom.runtimeProgressText.textContent = "-";
      }
    }

    if (dom.runOnceBtn) dom.runOnceBtn.disabled = jobRunning;
    if (dom.sendLatestBtn) dom.sendLatestBtn.disabled = jobRunning;
    if (dom.xhsLoginBtn) dom.xhsLoginBtn.disabled = jobRunning;
    if (dom.startDaemonBtn) dom.startDaemonBtn.disabled = daemonRunning;
    if (dom.stopDaemonBtn) dom.stopDaemonBtn.disabled = !daemonRunning;
    if (dom.stopJobBtn) dom.stopJobBtn.disabled = !jobRunning;

    if (state.prevJobRunning && !jobRunning) {
      loadSummaryAndRuns().catch(() => {});
      if (isWorkspaceView(state.view) && !hasUnsavedQuickEditChanges()) {
        loadLeads().catch(() => {});
      }
    }
    state.prevJobRunning = jobRunning;
  }

  function renderXhsAccountOptions(options, selected) {
    if (!dom.cfgXhsAccount) return;
    const list = Array.isArray(options) ? options : [];
    const safeSelected = String(selected || "default").trim() || "default";
    const uniq = new Map();
    uniq.set("default", { value: "default", label: "default", has_cookie: true });
    list.forEach((item) => {
      const value = String(item && item.value ? item.value : "").trim();
      if (!value) return;
      uniq.set(value, {
        value,
        label: String(item && item.label ? item.label : value),
        has_cookie: Boolean(item && item.has_cookie),
      });
    });
    if (!uniq.has(safeSelected)) {
      uniq.set(safeSelected, { value: safeSelected, label: safeSelected, has_cookie: false });
    }
    dom.cfgXhsAccount.innerHTML = Array.from(uniq.values())
      .map((item) => {
        const suffix = item.has_cookie ? "" : " (no-cookies)";
        return `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label + suffix)}</option>`;
      })
      .join("");
    dom.cfgXhsAccount.value = safeSelected;
  }

  function renderConfig(config) {
    state.config = config || {};
    const app = state.config.app || {};
    const xhs = state.config.xhs || {};
    const pipeline = state.config.pipeline || {};
    const agent = state.config.agent || {};
    const notify = state.config.notification || {};
    const email = state.config.email || {};
    const wechat = state.config.wechat_service || {};
    const llm = state.config.llm || {};
    const observability = state.config.observability || {};
    const alerts = observability.alerts || {};
    const fetchAlert = alerts.fetch_fail_streak && typeof alerts.fetch_fail_streak === "object" ? alerts.fetch_fail_streak : {};
    const llmAlert = alerts.llm_timeout_rate && typeof alerts.llm_timeout_rate === "object" ? alerts.llm_timeout_rate : {};
    const detailAlert = alerts.detail_missing_rate && typeof alerts.detail_missing_rate === "object" ? alerts.detail_missing_rate : {};
    renderXhsAccountOptions(xhs.account_options || [], xhs.account || "default");

    if (dom.cfgKeyword) dom.cfgKeyword.value = String(xhs.keyword || "");
    if (dom.cfgXhsAccountDir) dom.cfgXhsAccountDir.value = String(xhs.account_cookies_dir || "~/.xhs-mcp/accounts");
    if (dom.cfgSearchSort) dom.cfgSearchSort.value = String(xhs.search_sort || "time_descending");
    if (dom.cfgMaxResults) dom.cfgMaxResults.value = String(toInt(xhs.max_results, 20));
    if (dom.cfgMaxDetailFetch) dom.cfgMaxDetailFetch.value = String(toInt(xhs.max_detail_fetch, 5));
    if (dom.cfgDetailWorkers) dom.cfgDetailWorkers.value = String(toInt(xhs.detail_workers, 3));
    if (dom.cfgProcessWorkers) dom.cfgProcessWorkers.value = String(toInt(pipeline.process_workers, 4));
    if (dom.cfgAppInterval) dom.cfgAppInterval.value = String(toInt(app.interval_minutes, 15));
    if (dom.cfgAgentMode) dom.cfgAgentMode.value = String(agent.mode || "auto");
    if (dom.cfgNotifyMode) dom.cfgNotifyMode.value = String(notify.mode || "digest");
    if (dom.cfgDigestInterval) dom.cfgDigestInterval.value = String(toInt(notify.digest_interval_minutes, 30));
    if (dom.cfgDigestTop) dom.cfgDigestTop.value = String(toInt(notify.digest_top_summaries, 5));
    if (dom.cfgDigestNoNew) dom.cfgDigestNoNew.checked = Boolean(notify.digest_send_when_no_new);
    if (dom.cfgEmailEnabled) dom.cfgEmailEnabled.checked = Boolean(email.enabled);
    if (dom.cfgWechatEnabled) dom.cfgWechatEnabled.checked = Boolean(wechat.enabled);
    if (dom.cfgLlmEnabled) dom.cfgLlmEnabled.checked = Boolean(llm.enabled);
    if (dom.cfgLlmModel) dom.cfgLlmModel.value = String(llm.model || "");
    if (dom.cfgLlmBaseUrl) dom.cfgLlmBaseUrl.value = String(llm.base_url || "");
    if (dom.cfgAlertEnabled) dom.cfgAlertEnabled.checked = alerts.enabled !== false;
    if (dom.cfgAlertCooldown) dom.cfgAlertCooldown.value = String(toInt(alerts.cooldown_minutes, 60));
    const fetchShortThreshold = toInt(fetchAlert.short_threshold, toInt(alerts.fetch_fail_streak_threshold, 2));
    if (dom.cfgAlertFetchShortWindowRuns) dom.cfgAlertFetchShortWindowRuns.value = String(toInt(fetchAlert.short_window_runs, 1));
    if (dom.cfgAlertFetchStreak) dom.cfgAlertFetchStreak.value = String(fetchShortThreshold);
    if (dom.cfgAlertFetchShortMinRuns) dom.cfgAlertFetchShortMinRuns.value = String(toInt(fetchAlert.short_min_runs, 1));
    if (dom.cfgAlertFetchLongWindowRuns) dom.cfgAlertFetchLongWindowRuns.value = String(toInt(fetchAlert.long_window_runs, 6));
    if (dom.cfgAlertFetchLongThreshold) {
      const defaultLongThreshold = Math.max(1, Number(fetchShortThreshold || 2) * 0.6);
      dom.cfgAlertFetchLongThreshold.value = String(toFloat(fetchAlert.long_threshold, defaultLongThreshold));
    }
    if (dom.cfgAlertFetchLongMinRuns) dom.cfgAlertFetchLongMinRuns.value = String(toInt(fetchAlert.long_min_runs, 3));
    if (dom.cfgAlertLlmShortWindowRuns) dom.cfgAlertLlmShortWindowRuns.value = String(toInt(llmAlert.short_window_runs, 1));
    if (dom.cfgAlertLlmTimeoutRate) {
      const llmRatePct = Math.max(
        0,
        Math.min(
          100,
          Math.round(
            Number(
              llmAlert.short_threshold !== undefined
                ? llmAlert.short_threshold
                : (alerts.llm_timeout_rate_threshold || 0.35)
            ) * 100
          )
        )
      );
      dom.cfgAlertLlmTimeoutRate.value = String(llmRatePct);
    }
    const llmShortMinSamples = toInt(
      llmAlert.short_min_samples,
      toInt(alerts.llm_timeout_min_calls, 6)
    );
    if (dom.cfgAlertLlmTimeoutMinCalls) dom.cfgAlertLlmTimeoutMinCalls.value = String(llmShortMinSamples);
    if (dom.cfgAlertLlmLongWindowRuns) dom.cfgAlertLlmLongWindowRuns.value = String(toInt(llmAlert.long_window_runs, 8));
    if (dom.cfgAlertLlmLongThreshold) {
      const llmShortThreshold = toFloat(
        llmAlert.short_threshold,
        Number(alerts.llm_timeout_rate_threshold || 0.35)
      );
      const llmLongRatePct = Math.max(
        0,
        Math.min(100, Math.round(toFloat(llmAlert.long_threshold, llmShortThreshold * 0.7) * 100))
      );
      dom.cfgAlertLlmLongThreshold.value = String(llmLongRatePct);
    }
    if (dom.cfgAlertLlmLongMinSamples) {
      dom.cfgAlertLlmLongMinSamples.value = String(
        toInt(llmAlert.long_min_samples, Math.max(12, llmShortMinSamples * 3))
      );
    }
    if (dom.cfgAlertDetailShortWindowRuns) dom.cfgAlertDetailShortWindowRuns.value = String(toInt(detailAlert.short_window_runs, 1));
    if (dom.cfgAlertDetailMissingRate) {
      const detailRatePct = Math.max(
        0,
        Math.min(
          100,
          Math.round(
            Number(
              detailAlert.short_threshold !== undefined
                ? detailAlert.short_threshold
                : (alerts.detail_missing_rate_threshold || 0.45)
            ) * 100
          )
        )
      );
      dom.cfgAlertDetailMissingRate.value = String(detailRatePct);
    }
    const detailShortMinSamples = toInt(
      detailAlert.short_min_samples,
      toInt(alerts.detail_missing_min_samples, 6)
    );
    if (dom.cfgAlertDetailMissingMinSamples) dom.cfgAlertDetailMissingMinSamples.value = String(detailShortMinSamples);
    if (dom.cfgAlertDetailLongWindowRuns) dom.cfgAlertDetailLongWindowRuns.value = String(toInt(detailAlert.long_window_runs, 8));
    if (dom.cfgAlertDetailLongThreshold) {
      const detailShortThreshold = toFloat(
        detailAlert.short_threshold,
        Number(alerts.detail_missing_rate_threshold || 0.45)
      );
      const detailLongRatePct = Math.max(
        0,
        Math.min(100, Math.round(toFloat(detailAlert.long_threshold, detailShortThreshold * 0.7) * 100))
      );
      dom.cfgAlertDetailLongThreshold.value = String(detailLongRatePct);
    }
    if (dom.cfgAlertDetailLongMinSamples) {
      dom.cfgAlertDetailLongMinSamples.value = String(
        toInt(detailAlert.long_min_samples, Math.max(12, detailShortMinSamples * 3))
      );
    }
    if (dom.cfgAlertChannels) {
      const channels = Array.isArray(alerts.channels) ? alerts.channels.map((x) => String(x || "").trim()).filter(Boolean) : [];
      dom.cfgAlertChannels.value = channels.join(", ");
    }

    if (dom.runModeSelect) dom.runModeSelect.value = String(agent.mode || "auto");
    if (dom.daemonModeSelect) dom.daemonModeSelect.value = String(agent.mode || "auto");
    if (dom.daemonIntervalInput) dom.daemonIntervalInput.value = String(toInt(app.interval_minutes, 15));
    renderWizardGuide(state.config);
  }

  function renderWizardGuide(config) {
    if (!dom.wizardGuideSteps) return;

    const app = (config && config.app) || {};
    const xhs = (config && config.xhs) || {};
    const notify = (config && config.notification) || {};
    const email = (config && config.email) || {};
    const wechat = (config && config.wechat_service) || {};
    const llm = (config && config.llm) || {};

    const keyword = String(xhs.keyword || "").trim();
    const sort = String(xhs.search_sort || "");
    const step1 = Boolean(keyword.includes("继任") && sort === "time_descending");
    const step2 = Boolean(toInt(app.interval_minutes, 0) > 0 && toInt(notify.digest_interval_minutes, 0) > 0);
    const step3 = Boolean(notify.mode && String(notify.mode) !== "off");
    const step4 = Boolean(email.enabled || wechat.enabled);
    const step5 = Boolean(!llm.enabled || (String(llm.model || "").trim() && String(llm.base_url || "").trim()));

    const steps = [
      { label: "抓取参数：关键词=继任 + 时间排序", done: step1 },
      { label: "定时参数：主循环/摘要周期已填写", done: step2 },
      { label: "通知模式：digest 或 realtime", done: step3 },
      { label: "通知通道：至少启用邮件或微信", done: step4 },
      { label: "LLM 参数：启用时模型与地址完整", done: step5 },
    ];

    const doneCount = steps.filter((item) => item.done).length;
    const allDoneByConfig = doneCount === steps.length;
    const manualDone = localStorage.getItem(WIZARD_DONE_KEY) === "1";
    const finished = allDoneByConfig || manualDone;

    dom.wizardGuideSteps.innerHTML = steps
      .map((item) => {
        const cls = item.done ? "wizard-step done" : "wizard-step todo";
        const tag = item.done ? "完成" : "待处理";
        return `<div class="${cls}"><span class="wizard-step-tag">${tag}</span><span>${escapeHtml(item.label)}</span></div>`;
      })
      .join("");

    if (dom.wizardGuideBadge) {
      dom.wizardGuideBadge.textContent = finished ? "已完成" : `进行中 ${doneCount}/${steps.length}`;
    }
  }

  function renderSetupCheckResult(result) {
    const data = result || {};
    const summary = data.summary || {};
    const items = Array.isArray(data.items) ? data.items : [];
    const checkedAt = fmtTime(data.checked_at);
    const passed = toInt(summary.passed, 0);
    const warned = toInt(summary.warned, 0);
    const failed = toInt(summary.failed, 0);
    const total = toInt(summary.total, items.length);

    if (dom.wizardCheckSummary) {
      dom.wizardCheckSummary.textContent = `最近自检：${checkedAt} | 通过 ${passed} / ${total}，警告 ${warned}，失败 ${failed}`;
    }
    if (!dom.wizardCheckList) return;
    if (!items.length) {
      dom.wizardCheckList.innerHTML = '<p class="wizard-check-empty">暂无自检结果</p>';
      return;
    }

    const sortedItems = items.slice().sort((a, b) => {
      const rank = (status) => {
        const key = String(status || "").toLowerCase();
        if (key === "fail") return 0;
        if (key === "warn") return 1;
        return 2;
      };
      return rank(a && a.status) - rank(b && b.status);
    });

    const renderItem = (item) => {
        const status = String(item.status || "warn").toLowerCase();
        const statusText = status === "pass" ? "通过" : status === "fail" ? "失败" : "警告";
        const reason = String(item.reason || item.message || "").trim();
        const detail = String(item.detail || "").trim();
        const suggestion = String(item.suggestion || "").trim();
        const fixCommand = String(item.fix_command || "").trim();
        const openByDefault = status !== "pass";
        const openAttr = openByDefault ? " open" : "";
        const bodyHtml = [
          `<p>${escapeHtml(reason || "-")}</p>`,
          detail ? `<p class="wizard-check-detail">${escapeHtml(detail)}</p>` : "",
          suggestion ? `<p class="wizard-check-tip">建议：${escapeHtml(suggestion)}</p>` : "",
          fixCommand ? `<p class="wizard-check-tip">修复命令：<code>${escapeHtml(fixCommand)}</code></p>` : "",
        ]
          .filter(Boolean)
          .join("");
        return [
          `<details class="wizard-check-item ${status}"${openAttr}>`,
          `<summary class="wizard-check-head"><strong>${escapeHtml(String(item.name || "-"))}</strong><span class="wizard-check-status ${status}">${statusText}</span></summary>`,
          `<div class="wizard-check-body">${bodyHtml}</div>`,
          "</details>",
        ].join("");
    };

    dom.wizardCheckList.innerHTML = [
      '<div class="wizard-check-toolbar">',
      '<button type="button" class="btn ghost small" data-role="wizard-expand-all">展开全部</button>',
      '<button type="button" class="btn ghost small" data-role="wizard-collapse-all">收起通过项</button>',
      "</div>",
      ...sortedItems.map(renderItem),
    ].join("");
  }

  async function saveConfigForm(successMsg = "配置已保存") {
    const data = await postJson("/api/config", collectConfigPayload());
    renderConfig((data && data.config) || {});
    showToast((data && data.message) || successMsg, "success");
    await loadSummaryAndRuns();
  }

  function applyWizardPresetFields() {
    if (dom.cfgKeyword) dom.cfgKeyword.value = "继任";
    if (dom.cfgSearchSort) dom.cfgSearchSort.value = "time_descending";
    if (dom.cfgMaxResults) dom.cfgMaxResults.value = String(Math.max(20, toInt(dom.cfgMaxResults.value, 20)));
    if (dom.cfgMaxDetailFetch) dom.cfgMaxDetailFetch.value = String(Math.max(5, toInt(dom.cfgMaxDetailFetch.value, 5)));
    if (dom.cfgDetailWorkers) dom.cfgDetailWorkers.value = String(Math.max(3, toInt(dom.cfgDetailWorkers.value, 3)));
    if (dom.cfgProcessWorkers) dom.cfgProcessWorkers.value = String(Math.max(4, toInt(dom.cfgProcessWorkers.value, 4)));
    if (dom.cfgAppInterval) dom.cfgAppInterval.value = String(Math.max(15, toInt(dom.cfgAppInterval.value, 15)));
    if (dom.cfgNotifyMode) dom.cfgNotifyMode.value = "digest";
    if (dom.cfgDigestInterval) dom.cfgDigestInterval.value = String(Math.max(30, toInt(dom.cfgDigestInterval.value, 30)));
    if (dom.cfgDigestTop) dom.cfgDigestTop.value = String(Math.max(5, toInt(dom.cfgDigestTop.value, 5)));
    if (dom.cfgDigestNoNew) dom.cfgDigestNoNew.checked = false;
    if (dom.cfgAgentMode) dom.cfgAgentMode.value = "auto";
    if (dom.cfgAlertEnabled) dom.cfgAlertEnabled.checked = true;
    if (dom.cfgAlertCooldown) dom.cfgAlertCooldown.value = String(Math.max(30, toInt(dom.cfgAlertCooldown.value, 60)));
    if (dom.cfgAlertFetchShortWindowRuns) dom.cfgAlertFetchShortWindowRuns.value = String(Math.max(1, toInt(dom.cfgAlertFetchShortWindowRuns.value, 1)));
    if (dom.cfgAlertFetchStreak) dom.cfgAlertFetchStreak.value = String(Math.max(2, toInt(dom.cfgAlertFetchStreak.value, 2)));
    if (dom.cfgAlertFetchShortMinRuns) dom.cfgAlertFetchShortMinRuns.value = String(Math.max(1, toInt(dom.cfgAlertFetchShortMinRuns.value, 1)));
    if (dom.cfgAlertFetchLongWindowRuns) dom.cfgAlertFetchLongWindowRuns.value = String(Math.max(3, toInt(dom.cfgAlertFetchLongWindowRuns.value, 6)));
    if (dom.cfgAlertFetchLongThreshold) {
      const fetchShortThreshold = Math.max(2, toInt(dom.cfgAlertFetchStreak ? dom.cfgAlertFetchStreak.value : 2, 2));
      const fetchLongThreshold = Math.max(1, toFloat(dom.cfgAlertFetchLongThreshold.value, fetchShortThreshold * 0.6));
      dom.cfgAlertFetchLongThreshold.value = String(fetchLongThreshold);
    }
    if (dom.cfgAlertFetchLongMinRuns) dom.cfgAlertFetchLongMinRuns.value = String(Math.max(3, toInt(dom.cfgAlertFetchLongMinRuns.value, 3)));
    if (dom.cfgAlertLlmShortWindowRuns) dom.cfgAlertLlmShortWindowRuns.value = String(Math.max(1, toInt(dom.cfgAlertLlmShortWindowRuns.value, 1)));
    if (dom.cfgAlertLlmTimeoutRate) dom.cfgAlertLlmTimeoutRate.value = String(Math.max(20, toInt(dom.cfgAlertLlmTimeoutRate.value, 35)));
    if (dom.cfgAlertLlmTimeoutMinCalls) dom.cfgAlertLlmTimeoutMinCalls.value = String(Math.max(4, toInt(dom.cfgAlertLlmTimeoutMinCalls.value, 6)));
    if (dom.cfgAlertLlmLongWindowRuns) dom.cfgAlertLlmLongWindowRuns.value = String(Math.max(3, toInt(dom.cfgAlertLlmLongWindowRuns.value, 8)));
    if (dom.cfgAlertLlmLongThreshold) {
      const llmShortThreshold = Math.max(20, toInt(dom.cfgAlertLlmTimeoutRate ? dom.cfgAlertLlmTimeoutRate.value : 35, 35));
      dom.cfgAlertLlmLongThreshold.value = String(Math.max(10, toInt(dom.cfgAlertLlmLongThreshold.value, Math.round(llmShortThreshold * 0.7))));
    }
    if (dom.cfgAlertLlmLongMinSamples) dom.cfgAlertLlmLongMinSamples.value = String(Math.max(12, toInt(dom.cfgAlertLlmLongMinSamples.value, 18)));
    if (dom.cfgAlertDetailShortWindowRuns) dom.cfgAlertDetailShortWindowRuns.value = String(Math.max(1, toInt(dom.cfgAlertDetailShortWindowRuns.value, 1)));
    if (dom.cfgAlertDetailMissingRate) dom.cfgAlertDetailMissingRate.value = String(Math.max(30, toInt(dom.cfgAlertDetailMissingRate.value, 45)));
    if (dom.cfgAlertDetailMissingMinSamples) dom.cfgAlertDetailMissingMinSamples.value = String(Math.max(4, toInt(dom.cfgAlertDetailMissingMinSamples.value, 6)));
    if (dom.cfgAlertDetailLongWindowRuns) dom.cfgAlertDetailLongWindowRuns.value = String(Math.max(3, toInt(dom.cfgAlertDetailLongWindowRuns.value, 8)));
    if (dom.cfgAlertDetailLongThreshold) {
      const detailShortThreshold = Math.max(30, toInt(dom.cfgAlertDetailMissingRate ? dom.cfgAlertDetailMissingRate.value : 45, 45));
      dom.cfgAlertDetailLongThreshold.value = String(Math.max(15, toInt(dom.cfgAlertDetailLongThreshold.value, Math.round(detailShortThreshold * 0.7))));
    }
    if (dom.cfgAlertDetailLongMinSamples) dom.cfgAlertDetailLongMinSamples.value = String(Math.max(12, toInt(dom.cfgAlertDetailLongMinSamples.value, 18)));
  }

  async function runSetupCheck() {
    if (dom.wizardCheckBtn) dom.wizardCheckBtn.disabled = true;
    if (dom.wizardCheckSummary) dom.wizardCheckSummary.textContent = "正在执行一键自检，请稍候...";
    try {
      const result = await postJson("/api/setup/check", { include_network: true, include_xhs_status: true });
      renderSetupCheckResult(result || {});
      if (result && result.ok) {
        localStorage.setItem(WIZARD_DONE_KEY, "1");
      }
      renderWizardGuide(state.config || {});
      showToast(result && result.ok ? "自检通过" : "自检发现问题，请按建议处理", result && result.ok ? "success" : "error");
    } finally {
      if (dom.wizardCheckBtn) dom.wizardCheckBtn.disabled = false;
    }
  }

  function collectConfigPayload() {
    const alertChannels = String(dom.cfgAlertChannels ? dom.cfgAlertChannels.value : "")
      .split(",")
      .map((item) => item.trim())
      .filter((item) => item);
    const fetchShortWindowRuns = Math.max(1, toInt(dom.cfgAlertFetchShortWindowRuns ? dom.cfgAlertFetchShortWindowRuns.value : 1, 1));
    const fetchShortThreshold = Math.max(1, toInt(dom.cfgAlertFetchStreak ? dom.cfgAlertFetchStreak.value : 2, 2));
    const fetchShortMinRuns = Math.max(1, toInt(dom.cfgAlertFetchShortMinRuns ? dom.cfgAlertFetchShortMinRuns.value : 1, 1));
    const fetchLongWindowRuns = Math.max(1, toInt(dom.cfgAlertFetchLongWindowRuns ? dom.cfgAlertFetchLongWindowRuns.value : 6, 6));
    const fetchLongThreshold = Math.max(
      1,
      toFloat(dom.cfgAlertFetchLongThreshold ? dom.cfgAlertFetchLongThreshold.value : fetchShortThreshold * 0.6, fetchShortThreshold * 0.6)
    );
    const fetchLongMinRuns = Math.max(1, toInt(dom.cfgAlertFetchLongMinRuns ? dom.cfgAlertFetchLongMinRuns.value : 3, 3));
    const llmShortWindowRuns = Math.max(1, toInt(dom.cfgAlertLlmShortWindowRuns ? dom.cfgAlertLlmShortWindowRuns.value : 1, 1));
    const llmShortThresholdRate = Math.max(
      0,
      Math.min(1, toInt(dom.cfgAlertLlmTimeoutRate ? dom.cfgAlertLlmTimeoutRate.value : 35, 35) / 100)
    );
    const llmShortMinSamples = Math.max(1, toInt(dom.cfgAlertLlmTimeoutMinCalls ? dom.cfgAlertLlmTimeoutMinCalls.value : 6, 6));
    const llmLongWindowRuns = Math.max(1, toInt(dom.cfgAlertLlmLongWindowRuns ? dom.cfgAlertLlmLongWindowRuns.value : 8, 8));
    const llmLongThresholdRate = Math.max(
      0,
      Math.min(1, toInt(dom.cfgAlertLlmLongThreshold ? dom.cfgAlertLlmLongThreshold.value : Math.round(llmShortThresholdRate * 70), Math.round(llmShortThresholdRate * 70)) / 100)
    );
    const llmLongMinSamples = Math.max(1, toInt(dom.cfgAlertLlmLongMinSamples ? dom.cfgAlertLlmLongMinSamples.value : Math.max(12, llmShortMinSamples * 3), Math.max(12, llmShortMinSamples * 3)));
    const detailShortWindowRuns = Math.max(1, toInt(dom.cfgAlertDetailShortWindowRuns ? dom.cfgAlertDetailShortWindowRuns.value : 1, 1));
    const detailShortThresholdRate = Math.max(
      0,
      Math.min(1, toInt(dom.cfgAlertDetailMissingRate ? dom.cfgAlertDetailMissingRate.value : 45, 45) / 100)
    );
    const detailShortMinSamples = Math.max(1, toInt(dom.cfgAlertDetailMissingMinSamples ? dom.cfgAlertDetailMissingMinSamples.value : 6, 6));
    const detailLongWindowRuns = Math.max(1, toInt(dom.cfgAlertDetailLongWindowRuns ? dom.cfgAlertDetailLongWindowRuns.value : 8, 8));
    const detailLongThresholdRate = Math.max(
      0,
      Math.min(1, toInt(dom.cfgAlertDetailLongThreshold ? dom.cfgAlertDetailLongThreshold.value : Math.round(detailShortThresholdRate * 70), Math.round(detailShortThresholdRate * 70)) / 100)
    );
    const detailLongMinSamples = Math.max(1, toInt(dom.cfgAlertDetailLongMinSamples ? dom.cfgAlertDetailLongMinSamples.value : Math.max(12, detailShortMinSamples * 3), Math.max(12, detailShortMinSamples * 3)));
    return {
      app: {
        interval_minutes: toInt(dom.cfgAppInterval ? dom.cfgAppInterval.value : 15, 15),
      },
      xhs: {
        keyword: String(dom.cfgKeyword ? dom.cfgKeyword.value : "").trim(),
        account: String(dom.cfgXhsAccount ? dom.cfgXhsAccount.value : "default").trim() || "default",
        account_cookies_dir: String(dom.cfgXhsAccountDir ? dom.cfgXhsAccountDir.value : "~/.xhs-mcp/accounts").trim() || "~/.xhs-mcp/accounts",
        search_sort: String(dom.cfgSearchSort ? dom.cfgSearchSort.value : "time_descending"),
        max_results: toInt(dom.cfgMaxResults ? dom.cfgMaxResults.value : 20, 20),
        max_detail_fetch: toInt(dom.cfgMaxDetailFetch ? dom.cfgMaxDetailFetch.value : 5, 5),
        detail_workers: toInt(dom.cfgDetailWorkers ? dom.cfgDetailWorkers.value : 3, 3),
      },
      pipeline: {
        process_workers: toInt(dom.cfgProcessWorkers ? dom.cfgProcessWorkers.value : 4, 4),
      },
      agent: {
        mode: String(dom.cfgAgentMode ? dom.cfgAgentMode.value : "auto"),
      },
      notification: {
        mode: String(dom.cfgNotifyMode ? dom.cfgNotifyMode.value : "digest"),
        digest_interval_minutes: toInt(dom.cfgDigestInterval ? dom.cfgDigestInterval.value : 30, 30),
        digest_top_summaries: toInt(dom.cfgDigestTop ? dom.cfgDigestTop.value : 5, 5),
        digest_send_when_no_new: Boolean(dom.cfgDigestNoNew && dom.cfgDigestNoNew.checked),
      },
      email: {
        enabled: Boolean(dom.cfgEmailEnabled && dom.cfgEmailEnabled.checked),
      },
      wechat_service: {
        enabled: Boolean(dom.cfgWechatEnabled && dom.cfgWechatEnabled.checked),
      },
      llm: {
        enabled: Boolean(dom.cfgLlmEnabled && dom.cfgLlmEnabled.checked),
        model: String(dom.cfgLlmModel ? dom.cfgLlmModel.value : "").trim(),
        base_url: String(dom.cfgLlmBaseUrl ? dom.cfgLlmBaseUrl.value : "").trim(),
      },
      observability: {
        alerts: {
          enabled: Boolean(dom.cfgAlertEnabled && dom.cfgAlertEnabled.checked),
          cooldown_minutes: toInt(dom.cfgAlertCooldown ? dom.cfgAlertCooldown.value : 60, 60),
          fetch_fail_streak_threshold: fetchShortThreshold,
          llm_timeout_rate_threshold: llmShortThresholdRate,
          llm_timeout_min_calls: llmShortMinSamples,
          detail_missing_rate_threshold: detailShortThresholdRate,
          detail_missing_min_samples: detailShortMinSamples,
          fetch_fail_streak: {
            short_window_runs: fetchShortWindowRuns,
            short_threshold: fetchShortThreshold,
            short_min_runs: fetchShortMinRuns,
            long_window_runs: fetchLongWindowRuns,
            long_threshold: fetchLongThreshold,
            long_min_runs: fetchLongMinRuns,
          },
          llm_timeout_rate: {
            short_window_runs: llmShortWindowRuns,
            short_threshold: llmShortThresholdRate,
            short_min_samples: llmShortMinSamples,
            long_window_runs: llmLongWindowRuns,
            long_threshold: llmLongThresholdRate,
            long_min_samples: llmLongMinSamples,
          },
          detail_missing_rate: {
            short_window_runs: detailShortWindowRuns,
            short_threshold: detailShortThresholdRate,
            short_min_samples: detailShortMinSamples,
            long_window_runs: detailLongWindowRuns,
            long_threshold: detailLongThresholdRate,
            long_min_samples: detailLongMinSamples,
          },
          channels: alertChannels,
        },
      },
    };
  }

  async function loadSummaryAndRuns() {
    const [summary, runsResp, perfResp] = await Promise.all([
      fetchJson("/api/summary"),
      fetchJson("/api/runs?limit=20"),
      fetchJson("/api/performance?limit=60").catch(() => null),
    ]);
    const runItems = (runsResp && runsResp.items) || [];
    renderSummary(summary || {});
    renderRuns(runItems);
    const perfPayload = perfResp && typeof perfResp === "object" ? perfResp : buildPerformanceFromRuns(runItems);
    state.performance = perfPayload;
    renderPerformance(perfPayload);
    if (state.selectedRunId) {
      await loadRunDetail(state.selectedRunId).catch(() => {});
    }
  }

  async function loadLeads() {
    if (!isWorkspaceView(state.view)) return;
    const q = state.search.trim();
    const query = new URLSearchParams();
    query.set("limit", String(state.pagination.pageSize));
    query.set("page", String(state.pagination.page));
    query.set("view", state.view === "summary" ? "summary" : "all");
    query.set("status", String(state.leadFilters.status || "all"));
    query.set("dedupe", String(state.leadFilters.dedupe || "all"));
    if (q) query.set("q", q);

    const resp = await fetchJson(`/api/leads?${query.toString()}`);
    const items = (resp && resp.items) || [];
    state.leads = items;
    state.pagination.total = toInt(resp.total, items.length);
    state.pagination.page = toInt(resp.page, 1);
    state.pagination.pageSize = toInt(resp.page_size, state.pagination.pageSize);
    state.pagination.totalPages = Math.max(1, toInt(resp.total_pages, 1));

    renderLeads(items);
    renderPagination();
  }



  async function saveLeadEdit(form) {
    const noteId = String(form.getAttribute("data-note-id") || "").trim();
    if (!noteId) throw new Error("note_id 缺失");
    if (state.leadEditSaving) return;

    const selected = getSelectedLead() || {};
    const payloadFields = {};
    const formData = new FormData(form);
    for (const key of QUICK_EDIT_FIELDS) {
      const newValue = normalizeEditableText(formData.get(key));
      const prevValue = normalizeEditableText(selected[key]);
      if (newValue !== prevValue) {
        payloadFields[key] = newValue;
      }
    }
    if (!Object.keys(payloadFields).length) {
      showToast("没有字段变化，无需保存", "info");
      return;
    }

    const submitBtn = form.querySelector('[data-role="lead-edit-save"]');
    state.leadEditSaving = true;
    if (submitBtn) submitBtn.disabled = true;
    try {
      await postJson("/api/leads/update", {
        note_id: noteId,
        fields: payloadFields,
      });
      state.selectedNoteId = noteId;
      await loadLeads();
      showToast(`已保存 ${Object.keys(payloadFields).length} 个字段`, "success");
    } finally {
      state.leadEditSaving = false;
      if (submitBtn) submitBtn.disabled = false;
    }
  }

  async function loadRuntime() {
    const runtime = await fetchJson("/api/runtime");
    renderRuntime(runtime);
  }

  async function loadConfig() {
    const [resp, accountResp] = await Promise.all([
      fetchJson("/api/config"),
      fetchJson("/api/xhs/accounts").catch(() => null),
    ]);
    const config = (resp && resp.config) || {};
    if (!config.xhs) config.xhs = {};
    if (accountResp && typeof accountResp === "object") {
      if (Array.isArray(accountResp.options)) config.xhs.account_options = accountResp.options;
      if (accountResp.selected) config.xhs.account = accountResp.selected;
      if (accountResp.account_cookies_dir) config.xhs.account_cookies_dir = accountResp.account_cookies_dir;
    }
    renderConfig(config);
    optionalLoadWarned.config = false;
  }

  function renderResume(resume) {
    const data = resume || {};
    if (dom.resumeSourcePath) dom.resumeSourcePath.value = String(data.source_txt_path || "");
    if (dom.resumeTextPath) dom.resumeTextPath.value = String(data.resume_text_path || "");
    if (dom.resumeChars) dom.resumeChars.textContent = fmtInt(data.resume_chars || 0);
    if (dom.resumeSourceExists) dom.resumeSourceExists.textContent = data.source_exists ? "已存在" : "不存在";
    if (dom.resumeTextArea) dom.resumeTextArea.value = String(data.resume_text || data.resume_preview || "");
    if (dom.resumeParseBtn && !selectedResumeFile) {
      dom.resumeParseBtn.classList.add("hidden");
    }
  }

  async function loadResume() {
    const data = await fetchJson("/api/resume");
    renderResume(data || {});
    optionalLoadWarned.resume = false;
  }

  async function parseResumeFile(file) {
    if (!file) {
      throw new Error("请选择文件");
    }
    const form = new FormData();
    form.append("file", file, file.name || "resume.txt");
    try {
      return await postForm("/api/resume/parse", form);
    } catch (_err) {
      const base64 = await toBase64(file);
      return postJson("/api/resume/parse", {
        filename: String(file.name || "resume.txt"),
        mime_type: String(file.type || ""),
        content_base64: base64,
      });
    }
  }

  async function invokeAction(action, payload = {}) {
    const data = await postJson("/api/action", { action, ...payload });
    if (data && data.runtime) {
      renderRuntime(data.runtime);
    } else {
      await loadRuntime();
    }
    const ok = Boolean(data && data.ok);
    const msg = (data && data.message) || (ok ? "操作成功" : "操作失败");
    showToast(msg, ok ? "success" : "error");
    if (data && data.output && dom.runtimeLog) {
      dom.runtimeLog.textContent = String(data.output);
    }
    return data || {};
  }

  function normalizeView(nextView) {
    const allowed = new Set(["overview", "control", "leads", "summary"]);
    const view = String(nextView || "").trim().toLowerCase();
    return allowed.has(view) ? view : "overview";
  }

  function syncViewQuery(view, replace = false) {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("view", normalizeView(view));
      const statePayload = { view: normalizeView(view) };
      if (replace) {
        window.history.replaceState(statePayload, "", url.toString());
      } else {
        window.history.pushState(statePayload, "", url.toString());
      }
    } catch (_err) {}
  }

  async function switchView(nextView, options = {}) {
    const view = normalizeView(nextView);
    const pushHistory = options && options.pushHistory === true;
    const replaceHistory = options && options.replaceHistory === true;
    const loadData = !(options && options.loadData === false);

    const viewChanged = state.view !== view;
    if (!viewChanged && !loadData) {
      if (replaceHistory) syncViewQuery(view, true);
      return;
    }

    applyViewMode(view);

    if (pushHistory) syncViewQuery(view, false);
    if (replaceHistory) syncViewQuery(view, true);

    if (!loadData) return;

    if (state.view === "control") {
      await loadControlPanelData();
    } else if (isWorkspaceView(state.view)) {
      await loadLeads();
    }
  }

  function applyViewMode(nextView) {
    state.view = normalizeView(nextView);
    document.body.dataset.view = state.view;

    dom.navItems.forEach((item) => {
      const active = item.getAttribute("data-page") === state.view;
      item.classList.toggle("active", active);
    });

    const showControl = state.view === "control";
    const showWorkspace = isWorkspaceView(state.view);
    if (dom.controlSection) dom.controlSection.classList.toggle("hidden", !showControl);
    if (dom.workspace) dom.workspace.classList.toggle("hidden", !showWorkspace);
    if (dom.searchWrap) dom.searchWrap.classList.toggle("hidden", !showWorkspace);
    if (dom.searchInput) dom.searchInput.disabled = !showWorkspace;

    if (dom.searchInput) {
      if (state.view === "summary") {
        dom.searchInput.placeholder = "按摘要 / 岗位 / 公司筛选";
      } else if (state.view === "leads") {
        dom.searchInput.placeholder = "按岗位 / 公司 / 地点筛选";
      } else if (state.view === "overview") {
        dom.searchInput.placeholder = "总览页筛选（默认每页 10 条）";
      } else {
        dom.searchInput.placeholder = "控制中心无需搜索";
      }
    }

    state.pagination.pageSize = pageSizeForView(state.view);
    state.pagination.page = 1;
    if (dom.leadPageSize) dom.leadPageSize.value = String(state.pagination.pageSize);
    renderWorkspaceLayout();
    if (dom.detailBox) dom.detailBox.innerHTML = defaultDetailHtml();
    ensureEnhancedUi();
    renderPagination();
  }

  function renderRetryQueue(data) {
    state.retryQueueData = data || null;
    if (!dom.retryQueueBody) return;
    const summary = (data && data.summary) || {};
    const pending = (summary && summary.pending) || {};
    const running = (summary && summary.running) || {};
    const deadLetter = (summary && summary.dead_letter) || {};
    const stats = (summary && summary.stats) || {};
    const processingSuccess = toInt(stats.processing_success, 0);
    const processingFailed = toInt(stats.processing_failed, 0);
    const processedTotal = processingSuccess + processingFailed;
    const avgDurationMs = processedTotal > 0 ? Math.round(toInt(stats.total_duration_ms, 0) / processedTotal) : 0;

    if (dom.retryQueueSummary) {
      dom.retryQueueSummary.textContent =
        `待执行 ${fmtInt(pending.fetch || 0)}/${fmtInt(pending.llm_timeout || 0)}/${fmtInt(pending.email || 0)} · ` +
        `运行中 ${fmtInt(running.fetch || 0)}/${fmtInt(running.llm_timeout || 0)}/${fmtInt(running.email || 0)} · ` +
        `死信 ${fmtInt(deadLetter.fetch || 0)}/${fmtInt(deadLetter.llm_timeout || 0)}/${fmtInt(deadLetter.email || 0)} · ` +
        `处理 成功 ${fmtInt(processingSuccess)} / 失败 ${fmtInt(processingFailed)} · ` +
        `均时 ${fmtMs(avgDurationMs)}`;
    }
    if (dom.retryDeadSummary) {
      dom.retryDeadSummary.textContent = `总计 ${fmtInt(summary.dead_letters_total || 0)}`;
    }

    const items = Array.isArray(data && data.items) ? data.items : [];
    if (!items.length) {
      dom.retryQueueBody.innerHTML = `<tr><td colspan="7" class="table-tip">暂无队列数据</td></tr>`;
    } else {
      const statusLabel = (s) => {
        const v = String(s || "").toLowerCase();
        if (v === "pending") return "待执行";
        if (v === "running") return "执行中";
        if (v === "done") return "已完成";
        if (v === "dead_letter") return "死信";
        if (v === "dropped") return "已丢弃";
        return v || "-";
      };

      dom.retryQueueBody.innerHTML = items
        .slice(0, 120)
        .map((item) => {
          const id = toText(item.id, "");
          const qtype = toText(item.queue_type, "-");
          const action = toText(item.action, "-");
          const status = toText(item.status, "-");
          const attempt = `${fmtInt(item.attempt)} / ${fmtInt(item.max_attempts || 0)}`;
          const errCode = compactOneLine(item.last_error_code, "-", 32);
          const err = compactOneLine(item.last_error, "-", 120);
          const trace = compactOneLine(item.last_trace_id, "-", 42);
          const duration = fmtMs(item.last_duration_ms);
          const updated = fmtTime(item.updated_at);
          const dedupeKey = compactOneLine(item.dedupe_key, "", 26);
          const idemKey = compactOneLine(item.idempotency_key, "", 30);
          const keyParts = [];
          if (dedupeKey) keyParts.push(`dedupe:${dedupeKey}`);
          if (idemKey) keyParts.push(`idem:${idemKey}`);
          const keyLine = keyParts.length ? `<div class="sub-cell mono">${escapeHtml(keyParts.join(" | "))}</div>` : "";
          const disabled = String(status).toLowerCase() === "running" ? "disabled" : "";
          return `
            <tr data-retry-id="${escapeHtml(id)}">
              <td><div class="title-cell">${escapeHtml(qtype)}</div><div class="sub-cell">${escapeHtml(action)}</div>${keyLine}</td>
              <td>${escapeHtml(statusLabel(status))}</td>
              <td class="mono">${escapeHtml(attempt)}</td>
              <td><div class="mono retry-code">${escapeHtml(errCode)}</div><div class="sub-cell">${escapeHtml(err)}</div></td>
              <td><div class="mono">${escapeHtml(duration)}</div><div class="sub-cell mono">${escapeHtml(trace)}</div></td>
              <td>${escapeHtml(updated)}</td>
              <td class="retry-actions">
                <button class="btn ghost retry-requeue" type="button" ${disabled}>重试</button>
                <button class="btn ghost retry-drop" type="button" ${disabled}>丢弃</button>
              </td>
            </tr>
          `;
        })
        .join("");

      dom.retryQueueBody.querySelectorAll("tr[data-retry-id]").forEach((row) => {
        const id = String(row.getAttribute("data-retry-id") || "").trim();
        if (!id) return;
        const requeueBtn = row.querySelector(".retry-requeue");
        const dropBtn = row.querySelector(".retry-drop");
        if (requeueBtn) {
          requeueBtn.addEventListener("click", async (ev) => {
            ev.stopPropagation();
            try {
              await postJson("/api/retry-queue/requeue", { id });
              showToast("已加入重试", "success");
              await loadRetryQueue({ optional: true });
            } catch (err) {
              showToast(err instanceof Error ? err.message : String(err), "error");
            }
          });
        }
        if (dropBtn) {
          dropBtn.addEventListener("click", async (ev) => {
            ev.stopPropagation();
            try {
              await postJson("/api/retry-queue/drop", { id });
              showToast("已丢弃", "success");
              await loadRetryQueue({ optional: true });
            } catch (err) {
              showToast(err instanceof Error ? err.message : String(err), "error");
            }
          });
        }
      });
    }

    if (dom.retryDeadBody) {
      const deadLetters = Array.isArray(data && data.dead_letters) ? data.dead_letters : [];
      if (!deadLetters.length) {
        dom.retryDeadBody.innerHTML = `<tr><td colspan="4" class="table-tip">暂无死信记录</td></tr>`;
      } else {
        dom.retryDeadBody.innerHTML = deadLetters
          .slice(0, 100)
          .map((item) => {
            const qtype = toText(item.queue_type, "-");
            const action = toText(item.action, "-");
            const attempt = `${fmtInt(item.attempt)} / ${fmtInt(item.max_attempts || 0)}`;
            const code = compactOneLine(item.error_code, "-", 32);
            const reason = compactOneLine(item.reason, "-", 120);
            const deadAt = fmtTime(item.dead_lettered_at);
            return `
              <tr>
                <td><div class="title-cell">${escapeHtml(qtype)}</div><div class="sub-cell">${escapeHtml(action)}</div></td>
                <td class="mono">${escapeHtml(attempt)}</td>
                <td><div class="mono retry-code">${escapeHtml(code)}</div><div class="sub-cell">${escapeHtml(reason)}</div></td>
                <td>${escapeHtml(deadAt)}</td>
              </tr>
            `;
          })
          .join("");
      }
    }
  }

  async function loadRetryQueue(options = {}) {
    if (!dom.retryQueueBody) return;
    const optional = Boolean(options && options.optional);
    const query = new URLSearchParams();
    query.set("status", String(state.retryQueueFilters.status || "all"));
    query.set("queue_type", String(state.retryQueueFilters.queueType || "all"));
    query.set("limit", "120");
    try {
      const data = await fetchJson(`/api/retry-queue?${query.toString()}`);
      state.retryQueueUnavailable = false;
      retryQueueWarningShown = false;
      renderRetryQueue(data || null);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      const notFound = isApiNotFoundError(err);
      if (optional || notFound) {
        state.retryQueueUnavailable = true;
        renderRetryQueueUnavailable(notFound ? "当前后端版本未提供重试队列接口" : `重试队列暂不可用：${msg}`);
        if (!retryQueueWarningShown) {
          retryQueueWarningShown = true;
          showToast(notFound ? "重试队列接口未启用，已自动降级。" : `重试队列加载失败：${msg}`, "info");
        }
        return;
      }
      throw err;
    }
  }

  async function loadControlPanelData() {
    await Promise.all([
      loadConfig().catch((err) => {
        if (!optionalLoadWarned.config) {
          optionalLoadWarned.config = true;
          const msg = err instanceof Error ? err.message : String(err);
          showToast(`配置加载失败，已降级：${msg}`, "info");
        }
      }),
      loadResume().catch((err) => {
        if (!optionalLoadWarned.resume) {
          optionalLoadWarned.resume = true;
          const msg = err instanceof Error ? err.message : String(err);
          showToast(`简历加载失败，已降级：${msg}`, "info");
        }
      }),
      loadRetryQueue({ optional: true }),
    ]);
  }

  async function refreshAll() {
    if (state.loading) return;
    state.loading = true;
    if (dom.refreshBtn) dom.refreshBtn.disabled = true;
    setLoadingTable("正在加载实时数据...");

    try {
      await Promise.all([loadSummaryAndRuns(), loadRuntime()]);
      if (state.view === "control") {
        await loadControlPanelData();
      }
      if (isWorkspaceView(state.view)) {
        await loadLeads();
      } else {
        renderPagination();
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setTableError(`加载失败：${msg}`);
      if (dom.detailBox) dom.detailBox.innerHTML = `<h4>数据加载异常</h4><p>${escapeHtml(msg)}</p>`;
      showToast(`加载失败: ${msg}`, "error");
    } finally {
      state.loading = false;
      if (dom.refreshBtn) dom.refreshBtn.disabled = false;
    }
  }

  function loadSkin() {
    const cached = localStorage.getItem("successor_skin") || "";
    if (SKINS.includes(cached)) {
      state.skin = cached;
    }
    document.body.dataset.skin = state.skin;
  }

  function toggleSkin() {
    state.skin = state.skin === SKINS[0] ? SKINS[1] : SKINS[0];
    document.body.dataset.skin = state.skin;
    localStorage.setItem("successor_skin", state.skin);
  }

  function debounce(fn, wait) {
    let timer = null;
    return (...args) => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => fn(...args), wait);
    };
  }

  function setButtonBusy(button, busyText = "处理中...") {
    if (!button) return () => {};
    const idleText = String(button.dataset.idleText || button.textContent || "").trim();
    if (!button.dataset.idleText) {
      button.dataset.idleText = idleText;
    }
    button.dataset.busy = "1";
    button.classList.add("busy");
    button.disabled = true;
    button.textContent = String(busyText || "处理中...");
    return () => {
      button.dataset.busy = "0";
      button.classList.remove("busy");
      button.textContent = String(button.dataset.idleText || idleText || "");
      button.disabled = false;
    };
  }

  async function withBusyButton(button, busyText, task) {
    if (!button) return task();
    if (button.dataset.busy === "1") return;
    const restore = setButtonBusy(button, busyText);
    try {
      return await task();
    } finally {
      restore();
      if (state.runtime && typeof state.runtime === "object") {
        renderRuntime(state.runtime);
      }
    }
  }

  function bindEvents() {
    ensureEnhancedUi();

    if (dom.navItems && dom.navItems.length) {
      dom.navItems.forEach((item) => {
        item.addEventListener("click", (event) => {
          const isModified = event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0;
          if (isModified) return;
          const targetView = normalizeView(item.getAttribute("data-page"));
          event.preventDefault();
          switchView(targetView, { pushHistory: true }).catch((err) => {
            const msg = err instanceof Error ? err.message : String(err);
            showToast(msg, "error");
          });
        });
      });
    }

    window.addEventListener("popstate", () => {
      const params = new URLSearchParams(window.location.search || "");
      const targetView = normalizeView(params.get("view"));
      switchView(targetView, { loadData: true }).catch((err) => {
        const msg = err instanceof Error ? err.message : String(err);
        showToast(msg, "error");
      });
    });

    if (dom.refreshBtn) {
      dom.refreshBtn.addEventListener("click", () => {
        refreshAll();
      });
    }

    if (dom.skinBtn) {
      dom.skinBtn.addEventListener("click", () => {
        toggleSkin();
      });
    }

    if (dom.searchInput) {
      dom.searchInput.addEventListener(
        "input",
        debounce((event) => {
          state.search = String(event.target.value || "");
          state.pagination.page = 1;
          if (isWorkspaceView(state.view)) {
            loadLeads().catch((err) => {
              const msg = err instanceof Error ? err.message : String(err);
              setTableError(`搜索失败：${msg}`);
            });
          }
        }, 260),
      );
    }



    if (dom.detailBox) {
      dom.detailBox.addEventListener("submit", (event) => {
        const form = event.target && event.target.closest ? event.target.closest("form.quick-edit-form") : null;
        if (!form) return;
        event.preventDefault();
        saveLeadEdit(form).catch((err) => {
          showToast(err instanceof Error ? err.message : String(err), "error");
        });
      });
    }

    if (dom.leadPrevBtn) {
      dom.leadPrevBtn.addEventListener("click", () => {
        if (state.pagination.page <= 1) return;
        state.pagination.page -= 1;
        loadLeads().catch((err) => showToast(String(err), "error"));
      });
    }
    if (dom.leadNextBtn) {
      dom.leadNextBtn.addEventListener("click", () => {
        if (state.pagination.page >= state.pagination.totalPages) return;
        state.pagination.page += 1;
        loadLeads().catch((err) => showToast(String(err), "error"));
      });
    }
    if (dom.leadPageSize) {
      dom.leadPageSize.addEventListener("change", () => {
        const nextSize = toInt(dom.leadPageSize.value, pageSizeForView(state.view));
        rememberPageSizeForView(state.view, nextSize);
        state.pagination.pageSize = pageSizeForView(state.view);
        state.pagination.page = 1;
        loadLeads().catch((err) => showToast(String(err), "error"));
      });
    }

    if (dom.leadStatusFilter) {
      dom.leadStatusFilter.addEventListener("change", () => {
        state.leadFilters.status = String(dom.leadStatusFilter.value || "all");
        state.pagination.page = 1;
        if (isWorkspaceView(state.view)) {
          loadLeads().catch((err) => showToast(String(err), "error"));
        }
      });
    }
    if (dom.leadDedupeFilter) {
      dom.leadDedupeFilter.addEventListener("change", () => {
        state.leadFilters.dedupe = String(dom.leadDedupeFilter.value || "all");
        state.pagination.page = 1;
        if (isWorkspaceView(state.view)) {
          loadLeads().catch((err) => showToast(String(err), "error"));
        }
      });
    }

    if (dom.retryQueueStatusFilter) {
      dom.retryQueueStatusFilter.addEventListener("change", () => {
        state.retryQueueFilters.status = String(dom.retryQueueStatusFilter.value || "all");
        loadRetryQueue({ optional: true }).catch(() => {});
      });
    }
    if (dom.retryQueueTypeFilter) {
      dom.retryQueueTypeFilter.addEventListener("change", () => {
        state.retryQueueFilters.queueType = String(dom.retryQueueTypeFilter.value || "all");
        loadRetryQueue({ optional: true }).catch(() => {});
      });
    }
    if (dom.retryQueueRefreshBtn) {
      dom.retryQueueRefreshBtn.addEventListener("click", () => {
        withBusyButton(dom.retryQueueRefreshBtn, "刷新中...", async () => {
          await loadRetryQueue({ optional: true });
        }).catch((err) => showToast(String(err), "error"));
      });
    }
    if (dom.retryQueueReplayBtn) {
      dom.retryQueueReplayBtn.addEventListener("click", async () => {
        withBusyButton(dom.retryQueueReplayBtn, "触发中...", async () => {
          const payload = { queue_type: String(state.retryQueueFilters.queueType || "all"), limit: 120 };
          const resp = await postJson("/api/retry-queue/kick", payload);
          const kicked = toInt(resp && resp.kicked, 0);
          showToast(`已触发待执行重试 ${kicked} 条`, "success");
          await loadRetryQueue({ optional: true });
        }).catch((err) => {
          showToast(err instanceof Error ? err.message : String(err), "error");
        });
      });
    }

    if (dom.runOnceBtn) {
      dom.runOnceBtn.addEventListener("click", async () => {
        withBusyButton(dom.runOnceBtn, "抓取中...", async () => {
          await invokeAction("run_once", { mode: dom.runModeSelect ? dom.runModeSelect.value : "auto" });
        }).catch((err) => {
          showToast(err instanceof Error ? err.message : String(err), "error");
        });
      });
    }
    if (dom.sendLatestBtn) {
      dom.sendLatestBtn.addEventListener("click", async () => {
        withBusyButton(dom.sendLatestBtn, "发送中...", async () => {
          await invokeAction("send_latest", { limit: toInt(dom.sendLatestInput ? dom.sendLatestInput.value : 5, 5) });
        }).catch((err) => {
          showToast(err instanceof Error ? err.message : String(err), "error");
        });
      });
    }
    if (dom.xhsLoginBtn) {
      dom.xhsLoginBtn.addEventListener("click", async () => {
        withBusyButton(dom.xhsLoginBtn, "登录中...", async () => {
          await invokeAction("xhs_login", { timeout_seconds: toInt(dom.loginTimeoutInput ? dom.loginTimeoutInput.value : 180, 180) });
        }).catch((err) => {
          showToast(err instanceof Error ? err.message : String(err), "error");
        });
      });
    }
    if (dom.xhsStatusBtn) {
      dom.xhsStatusBtn.addEventListener("click", async () => {
        withBusyButton(dom.xhsStatusBtn, "检查中...", async () => {
          const data = await invokeAction("xhs_status", {});
          if (data && data.status && typeof data.status === "object") {
            showToast(`登录状态: ${JSON.stringify(data.status)}`, data.ok ? "success" : "error");
          }
        }).catch((err) => {
          showToast(err instanceof Error ? err.message : String(err), "error");
        });
      });
    }
    if (dom.startDaemonBtn) {
      dom.startDaemonBtn.addEventListener("click", async () => {
        withBusyButton(dom.startDaemonBtn, "启动中...", async () => {
          await invokeAction("start_daemon", {
            mode: dom.daemonModeSelect ? dom.daemonModeSelect.value : "auto",
            interval_minutes: toInt(dom.daemonIntervalInput ? dom.daemonIntervalInput.value : 15, 15),
          });
        }).catch((err) => {
          showToast(err instanceof Error ? err.message : String(err), "error");
        });
      });
    }
    if (dom.stopDaemonBtn) {
      dom.stopDaemonBtn.addEventListener("click", async () => {
        withBusyButton(dom.stopDaemonBtn, "停止中...", async () => {
          await invokeAction("stop_daemon", {});
        }).catch((err) => {
          showToast(err instanceof Error ? err.message : String(err), "error");
        });
      });
    }
    if (dom.stopJobBtn) {
      dom.stopJobBtn.addEventListener("click", async () => {
        withBusyButton(dom.stopJobBtn, "停止中...", async () => {
          await invokeAction("stop_job", {});
        }).catch((err) => {
          showToast(err instanceof Error ? err.message : String(err), "error");
        });
      });
    }
    if (dom.reloadConfigBtn) {
      dom.reloadConfigBtn.addEventListener("click", async () => {
        withBusyButton(dom.reloadConfigBtn, "重载中...", async () => {
          await loadConfig();
          showToast("配置已重载", "success");
        }).catch((err) => {
          showToast(err instanceof Error ? err.message : String(err), "error");
        });
      });
    }
    if (dom.saveConfigBtn) {
      dom.saveConfigBtn.addEventListener("click", async () => {
        withBusyButton(dom.saveConfigBtn, "保存中...", async () => {
          await saveConfigForm("配置已保存");
        }).catch((err) => {
          showToast(err instanceof Error ? err.message : String(err), "error");
        });
      });
    }
    if (dom.wizardApplyBtn) {
      dom.wizardApplyBtn.addEventListener("click", async () => {
        withBusyButton(dom.wizardApplyBtn, "应用中...", async () => {
          applyWizardPresetFields();
          await saveConfigForm("向导推荐配置已应用");
          showToast("推荐配置已应用，可继续执行一键自检", "success");
        }).catch((err) => {
          showToast(err instanceof Error ? err.message : String(err), "error");
        });
      });
    }
    if (dom.wizardCheckBtn) {
      dom.wizardCheckBtn.addEventListener("click", async () => {
        withBusyButton(dom.wizardCheckBtn, "检测中...", async () => {
          await runSetupCheck();
        }).catch((err) => {
          showToast(err instanceof Error ? err.message : String(err), "error");
        });
      });
    }
    if (dom.wizardCheckList) {
      dom.wizardCheckList.addEventListener("click", (event) => {
        const target = event.target && event.target.closest ? event.target.closest("[data-role]") : null;
        if (!target) return;
        const role = String(target.getAttribute("data-role") || "").trim();
        if (!role) return;
        const details = Array.from(dom.wizardCheckList.querySelectorAll("details.wizard-check-item"));
        if (!details.length) return;
        if (role === "wizard-expand-all") {
          details.forEach((item) => {
            item.open = true;
          });
          return;
        }
        if (role === "wizard-collapse-all") {
          details.forEach((item) => {
            const isPass = item.classList.contains("pass");
            item.open = !isPass;
          });
        }
      });
    }
    if (dom.wizardMarkDoneBtn) {
      dom.wizardMarkDoneBtn.addEventListener("click", () => {
        localStorage.setItem(WIZARD_DONE_KEY, "1");
        renderWizardGuide(state.config || {});
        showToast("已标记向导完成", "success");
      });
    }
    if (dom.resumeFileInput) {
      dom.resumeFileInput.addEventListener("change", () => {
        selectedResumeFile = dom.resumeFileInput && dom.resumeFileInput.files ? dom.resumeFileInput.files[0] : null;
        if (dom.resumeParseBtn) {
          dom.resumeParseBtn.classList.toggle("hidden", !selectedResumeFile);
        }
      });
    }
    if (dom.resumeParseBtn) {
      dom.resumeParseBtn.addEventListener("click", async () => {
        withBusyButton(dom.resumeParseBtn, "解析中...", async () => {
          const data = await parseResumeFile(selectedResumeFile);
          if (dom.resumeTextArea) {
            dom.resumeTextArea.value = String((data && data.resume_text) || "");
          }
          if (dom.resumeChars) {
            dom.resumeChars.textContent = fmtInt((data && data.resume_chars) || 0);
          }
          showToast("文件解析完成，已覆盖文本框", "success");
        }).catch((err) => {
          showToast(err instanceof Error ? err.message : String(err), "error");
        });
      });
    }
    if (dom.resumeUploadBtn) {
      dom.resumeUploadBtn.addEventListener("click", async () => {
        withBusyButton(dom.resumeUploadBtn, "上传中...", async () => {
          const text = String(dom.resumeTextArea ? dom.resumeTextArea.value : "");
          const data = await postJson("/api/resume/text", { resume_text: text });
          showToast((data && data.message) || "简历上传成功", "success");
          await loadResume();
        }).catch((err) => {
          showToast(err instanceof Error ? err.message : String(err), "error");
        });
      });
    }
  }

  function initAutoRefresh() {
    const refreshCore = () => {
      if (document.hidden) return;
      loadSummaryAndRuns().catch(() => {});
      loadRuntime().catch(() => {});
      if (state.view === "control") {
        loadRetryQueue({ optional: true }).catch(() => {});
      }
    };

    const refreshLeads = () => {
      if (document.hidden) return;
      if (isWorkspaceView(state.view)) {
        if (hasUnsavedQuickEditChanges()) return;
        loadLeads().catch(() => {});
      }
    };

    setInterval(refreshCore, 12000);
    setInterval(refreshLeads, 25000);

    document.addEventListener("visibilitychange", () => {
      if (document.hidden) return;
      refreshCore();
      refreshLeads();
    });
  }

  function boot() {
    window.__spLoadRunDetail = (runId) =>
      loadRunDetail(runId).catch((err) => {
        const msg = err instanceof Error ? err.message : String(err);
        if (workspaceVue && typeof workspaceVue.applyRunDetail === "function") {
          workspaceVue.applyRunDetail({ run_id: runId, recorded_at: "", failed_stages: [], fetch_fail_events: [] });
          workspaceVue.runDetailHtml = `<p class="table-tip error">${escapeHtml(msg)}</p>`;
        } else if (dom.runDetailBox) {
          dom.runDetailBox.innerHTML = `<p class="table-tip error">${escapeHtml(msg)}</p>`;
        }
      });
    loadSkin();
    loadPageSizePrefs();
    applyViewMode(state.view);
    syncViewQuery(state.view, true);
    bindEvents();
    refreshAll();
    initAutoRefresh();
  }

  boot();
})();
