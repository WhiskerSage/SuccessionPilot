(() => {
  const startView = String(document.body.dataset.startView || "overview").trim().toLowerCase();

  const state = {
    leads: [],
    selectedNoteId: "",
    loading: false,
    skin: "business-blue",
    search: "",
    view: startView || "overview",
    runItems: [],
    runtime: null,
    config: null,
    prevJobRunning: false,
    pagination: {
      page: 1,
      pageSize: 30,
      total: 0,
      totalPages: 1,
    },
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
    runList: document.getElementById("runList"),
    searchInput: document.getElementById("searchInput"),
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
    cfgSearchSort: document.getElementById("cfgSearchSort"),
    cfgMaxResults: document.getElementById("cfgMaxResults"),
    cfgMaxDetailFetch: document.getElementById("cfgMaxDetailFetch"),
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
  };

  const SKINS = ["business-blue", "graphite-office"];
  const API_BASES = (() => {
    const candidates = ["", "http://127.0.0.1:8787", "http://localhost:8787"];
    if (window.location.protocol === "file:") {
      return candidates.filter((item) => item);
    }
    return candidates;
  })();
  const DEFAULT_DETAIL = `
    <h4>请选择一条线索</h4>
    <p>这里会展示岗位摘要、JD、评论预览和原帖详情内容。</p>
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
      const ts = Date.parse(text);
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
        if (!resp.ok) {
          const text = await resp.text();
          throw new Error(`${resp.status} ${resp.statusText} ${text}`.trim());
        }
        const contentType = resp.headers.get("Content-Type") || "";
        if (contentType.includes("application/json")) {
          return await resp.json();
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

  function pageSizeForView(view) {
    if (view === "overview") return 10;
    if (view === "summary") return 20;
    return 30;
  }

  function isWorkspaceView(view) {
    return view !== "control";
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

  function renderRuns(items) {
    state.runItems = Array.isArray(items) ? items : [];
    if (!dom.runList) return;
    if (!state.runItems.length) {
      dom.runList.innerHTML = "<li>暂无运行记录</li>";
      return;
    }
    dom.runList.innerHTML = state.runItems
      .map((item) => {
        const runId = toText(item.run_id);
        const t = fmtTime(item.recorded_at);
        const fetched = fmtInt(item.fetched);
        const jobs = fmtInt(item.jobs);
        const sent = fmtInt(item.send_logs);
        const digest = item.digest_sent ? "摘要已发" : "摘要未发";
        return `<li><strong>${escapeHtml(runId)}</strong> · ${escapeHtml(t)} · 抓取 ${fetched} / 岗位 ${jobs} / 发送 ${sent} · ${digest}</li>`;
      })
      .join("");
  }

  function renderPagination() {
    if (!dom.leadPageInfo || !dom.leadPrevBtn || !dom.leadNextBtn || !dom.leadPager) return;
    const { page, totalPages, total, pageSize } = state.pagination;
    dom.leadPageInfo.textContent = `${page} / ${totalPages} · 共 ${fmtInt(total)} 条`;
    dom.leadPrevBtn.disabled = page <= 1;
    dom.leadNextBtn.disabled = page >= totalPages;
    dom.leadPager.classList.toggle("hidden", !isWorkspaceView(state.view));
    if (dom.leadPageSize) {
      dom.leadPageSize.value = String(pageSize);
    }
  }

  function getSelectedLead() {
    if (!state.leads.length) return null;
    const byId = state.leads.find((x) => x.note_id === state.selectedNoteId);
    if (byId) return byId;
    state.selectedNoteId = state.leads[0].note_id;
    return state.leads[0];
  }

  function compactText(value, limit = 2200) {
    const text = String(value ?? "").trim();
    if (!text) return "";
    if (text.length <= limit) return text;
    return `${text.slice(0, limit)}\n...（界面展示已截断，共 ${text.length} 字）`;
  }

  function renderDetail(lead) {
    if (!dom.detailBox) return;
    if (!lead) {
      dom.detailBox.innerHTML = DEFAULT_DETAIL;
      return;
    }

    const title = toText(lead.title);
    const author = toText(lead.author);
    const publish = toText(lead.publish_time_text || lead.publish_time);
    const company = toText(lead.company);
    const position = toText(lead.position);
    const location = toText(lead.location);
    const req = compactText(lead.requirements, 1200) || "暂无";
    const summary = compactText(lead.summary, 3600) || "暂无摘要";
    const comments = compactText(lead.comments_preview, 1600) || "暂无评论预览";
    const detailText = compactText(lead.detail_text, 2600) || "暂无正文详情";
    const risk = compactText(lead.risk_flags, 360) || "无";
    const url = String(lead.url || "").trim();

    dom.detailBox.innerHTML = `
      <h4>${escapeHtml(title)}</h4>
      <div class="meta-line">作者：${escapeHtml(author)} | 发布时间：${escapeHtml(publish)} | ID：<span class="mono">${escapeHtml(toText(lead.note_id))}</span></div>
      <div class="detail-grid">
        <div class="detail-item"><span>公司</span><strong>${escapeHtml(company)}</strong></div>
        <div class="detail-item"><span>岗位</span><strong>${escapeHtml(position)}</strong></div>
        <div class="detail-item"><span>地点</span><strong>${escapeHtml(location)}</strong></div>
        <div class="detail-item"><span>互动</span><strong>赞 ${fmtInt(lead.like_count)} / 评 ${fmtInt(lead.comment_count)} / 转 ${fmtInt(lead.share_count)}</strong></div>
      </div>
      <div class="detail-block"><h5>结构化要求</h5><pre>${escapeHtml(req)}</pre></div>
      <div class="detail-block"><h5>摘要</h5><pre>${escapeHtml(summary)}</pre></div>
      <div class="detail-block"><h5>评论预览</h5><pre>${escapeHtml(comments)}</pre></div>
      <div class="detail-block"><h5>原帖正文详情</h5><pre>${escapeHtml(detailText)}</pre></div>
      <div class="meta-line">风险标签：${escapeHtml(risk)}</div>
      ${url ? `<div class="detail-link"><a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">打开原帖链接</a></div>` : ""}
    `;
  }

  function renderLeads(items) {
    state.leads = Array.isArray(items) ? items : [];
    if (dom.leadCount) dom.leadCount.textContent = `${state.leads.length} 条`;

    if (!dom.leadBody) return;
    if (!state.leads.length) {
      dom.leadBody.innerHTML = '<tr><td colspan="5" class="table-tip">暂无匹配线索</td></tr>';
      state.selectedNoteId = "";
      renderDetail(null);
      return;
    }

    if (!state.selectedNoteId || !state.leads.some((x) => x.note_id === state.selectedNoteId)) {
      state.selectedNoteId = state.leads[0].note_id;
    }

    dom.leadBody.innerHTML = state.leads
      .map((lead) => {
        const active = lead.note_id === state.selectedNoteId ? "active" : "";
        const publish = toText(lead.publish_time_text || fmtTime(lead.publish_time));
        const jobLine = `${toText(lead.position, "岗位待补充")} / ${toText(lead.company, "公司待补充")}`;
        const location = toText(lead.location);
        const interact = `赞 ${fmtInt(lead.like_count)} / 评 ${fmtInt(lead.comment_count)}`;
        const badge = statusBadge(lead.status, lead.like_count, lead.comment_count);

        return `
          <tr class="${active}" data-id="${escapeHtml(lead.note_id)}">
            <td>${escapeHtml(publish)}</td>
            <td><div class="title-cell">${escapeHtml(jobLine)}</div><div class="sub-cell">${escapeHtml(toText(lead.title))}</div></td>
            <td>${escapeHtml(location)}</td>
            <td>${escapeHtml(interact)}</td>
            <td>${badge}</td>
          </tr>
        `;
      })
      .join("");

    const rows = dom.leadBody.querySelectorAll("tr[data-id]");
    rows.forEach((row) => {
      row.addEventListener("click", () => {
        state.selectedNoteId = row.getAttribute("data-id") || "";
        renderLeads(state.leads);
      });
    });
    renderDetail(getSelectedLead());
  }

  function setLoadingTable(message = "加载中...") {
    if (!dom.leadBody) return;
    dom.leadBody.innerHTML = `<tr><td colspan="5" class="table-tip">${escapeHtml(message)}</td></tr>`;
  }

  function setTableError(message) {
    if (!dom.leadBody) return;
    dom.leadBody.innerHTML = `<tr><td colspan="5" class="table-tip error">${escapeHtml(message)}</td></tr>`;
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

    if (dom.runOnceBtn) dom.runOnceBtn.disabled = jobRunning;
    if (dom.sendLatestBtn) dom.sendLatestBtn.disabled = jobRunning;
    if (dom.xhsLoginBtn) dom.xhsLoginBtn.disabled = jobRunning;
    if (dom.startDaemonBtn) dom.startDaemonBtn.disabled = daemonRunning;
    if (dom.stopDaemonBtn) dom.stopDaemonBtn.disabled = !daemonRunning;
    if (dom.stopJobBtn) dom.stopJobBtn.disabled = !jobRunning;

    if (state.prevJobRunning && !jobRunning) {
      loadSummaryAndRuns().catch(() => {});
      if (isWorkspaceView(state.view)) {
        loadLeads().catch(() => {});
      }
    }
    state.prevJobRunning = jobRunning;
  }

  function renderConfig(config) {
    state.config = config || {};
    const app = state.config.app || {};
    const xhs = state.config.xhs || {};
    const agent = state.config.agent || {};
    const notify = state.config.notification || {};
    const email = state.config.email || {};
    const wechat = state.config.wechat_service || {};
    const llm = state.config.llm || {};

    if (dom.cfgKeyword) dom.cfgKeyword.value = String(xhs.keyword || "");
    if (dom.cfgSearchSort) dom.cfgSearchSort.value = String(xhs.search_sort || "time_descending");
    if (dom.cfgMaxResults) dom.cfgMaxResults.value = String(toInt(xhs.max_results, 20));
    if (dom.cfgMaxDetailFetch) dom.cfgMaxDetailFetch.value = String(toInt(xhs.max_detail_fetch, 5));
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

    if (dom.runModeSelect) dom.runModeSelect.value = String(agent.mode || "auto");
    if (dom.daemonModeSelect) dom.daemonModeSelect.value = String(agent.mode || "auto");
    if (dom.daemonIntervalInput) dom.daemonIntervalInput.value = String(toInt(app.interval_minutes, 15));
  }

  function collectConfigPayload() {
    return {
      app: {
        interval_minutes: toInt(dom.cfgAppInterval ? dom.cfgAppInterval.value : 15, 15),
      },
      xhs: {
        keyword: String(dom.cfgKeyword ? dom.cfgKeyword.value : "").trim(),
        search_sort: String(dom.cfgSearchSort ? dom.cfgSearchSort.value : "time_descending"),
        max_results: toInt(dom.cfgMaxResults ? dom.cfgMaxResults.value : 20, 20),
        max_detail_fetch: toInt(dom.cfgMaxDetailFetch ? dom.cfgMaxDetailFetch.value : 5, 5),
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
    };
  }

  async function loadSummaryAndRuns() {
    const [summary, runsResp] = await Promise.all([fetchJson("/api/summary"), fetchJson("/api/runs?limit=10")]);
    renderSummary(summary || {});
    renderRuns((runsResp && runsResp.items) || []);
  }

  async function loadLeads() {
    if (!isWorkspaceView(state.view)) return;
    const q = state.search.trim();
    const query = new URLSearchParams();
    query.set("limit", String(state.pagination.pageSize));
    query.set("page", String(state.pagination.page));
    query.set("view", state.view === "summary" ? "summary" : "all");
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

  async function loadRuntime() {
    const runtime = await fetchJson("/api/runtime");
    renderRuntime(runtime);
  }

  async function loadConfig() {
    const resp = await fetchJson("/api/config");
    renderConfig((resp && resp.config) || {});
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

  function applyViewMode(nextView) {
    const allowed = new Set(["overview", "control", "leads", "summary"]);
    state.view = allowed.has(nextView) ? nextView : "overview";
    document.body.dataset.view = state.view;

    dom.navItems.forEach((item) => {
      const active = item.getAttribute("data-page") === state.view;
      item.classList.toggle("active", active);
    });

    const showControl = state.view === "control";
    const showWorkspace = isWorkspaceView(state.view);
    if (dom.controlSection) dom.controlSection.classList.toggle("hidden", !showControl);
    if (dom.workspace) dom.workspace.classList.toggle("hidden", !showWorkspace);
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
    renderPagination();
  }

  async function refreshAll() {
    if (state.loading) return;
    state.loading = true;
    if (dom.refreshBtn) dom.refreshBtn.disabled = true;
    setLoadingTable("正在加载实时数据...");

    try {
      await Promise.all([loadSummaryAndRuns(), loadRuntime(), loadConfig()]);
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

  function bindEvents() {
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
        state.pagination.pageSize = toInt(dom.leadPageSize.value, 30);
        state.pagination.page = 1;
        loadLeads().catch((err) => showToast(String(err), "error"));
      });
    }

    if (dom.runOnceBtn) {
      dom.runOnceBtn.addEventListener("click", async () => {
        try {
          await invokeAction("run_once", { mode: dom.runModeSelect ? dom.runModeSelect.value : "auto" });
        } catch (err) {
          showToast(err instanceof Error ? err.message : String(err), "error");
        }
      });
    }
    if (dom.sendLatestBtn) {
      dom.sendLatestBtn.addEventListener("click", async () => {
        try {
          await invokeAction("send_latest", { limit: toInt(dom.sendLatestInput ? dom.sendLatestInput.value : 5, 5) });
        } catch (err) {
          showToast(err instanceof Error ? err.message : String(err), "error");
        }
      });
    }
    if (dom.xhsLoginBtn) {
      dom.xhsLoginBtn.addEventListener("click", async () => {
        try {
          await invokeAction("xhs_login", { timeout_seconds: toInt(dom.loginTimeoutInput ? dom.loginTimeoutInput.value : 180, 180) });
        } catch (err) {
          showToast(err instanceof Error ? err.message : String(err), "error");
        }
      });
    }
    if (dom.xhsStatusBtn) {
      dom.xhsStatusBtn.addEventListener("click", async () => {
        try {
          const data = await invokeAction("xhs_status", {});
          if (data && data.status && typeof data.status === "object") {
            showToast(`登录状态: ${JSON.stringify(data.status)}`, data.ok ? "success" : "error");
          }
        } catch (err) {
          showToast(err instanceof Error ? err.message : String(err), "error");
        }
      });
    }
    if (dom.startDaemonBtn) {
      dom.startDaemonBtn.addEventListener("click", async () => {
        try {
          await invokeAction("start_daemon", {
            mode: dom.daemonModeSelect ? dom.daemonModeSelect.value : "auto",
            interval_minutes: toInt(dom.daemonIntervalInput ? dom.daemonIntervalInput.value : 15, 15),
          });
        } catch (err) {
          showToast(err instanceof Error ? err.message : String(err), "error");
        }
      });
    }
    if (dom.stopDaemonBtn) {
      dom.stopDaemonBtn.addEventListener("click", async () => {
        try {
          await invokeAction("stop_daemon", {});
        } catch (err) {
          showToast(err instanceof Error ? err.message : String(err), "error");
        }
      });
    }
    if (dom.stopJobBtn) {
      dom.stopJobBtn.addEventListener("click", async () => {
        try {
          await invokeAction("stop_job", {});
        } catch (err) {
          showToast(err instanceof Error ? err.message : String(err), "error");
        }
      });
    }
    if (dom.reloadConfigBtn) {
      dom.reloadConfigBtn.addEventListener("click", async () => {
        try {
          await loadConfig();
          showToast("配置已重载", "success");
        } catch (err) {
          showToast(err instanceof Error ? err.message : String(err), "error");
        }
      });
    }
    if (dom.saveConfigBtn) {
      dom.saveConfigBtn.addEventListener("click", async () => {
        try {
          const data = await postJson("/api/config", collectConfigPayload());
          renderConfig((data && data.config) || {});
          showToast((data && data.message) || "配置已保存", "success");
          await loadSummaryAndRuns();
        } catch (err) {
          showToast(err instanceof Error ? err.message : String(err), "error");
        }
      });
    }
  }

  function initAutoRefresh() {
    setInterval(() => {
      loadSummaryAndRuns().catch(() => {});
      loadRuntime().catch(() => {});
    }, 12000);

    setInterval(() => {
      if (isWorkspaceView(state.view)) {
        loadLeads().catch(() => {});
      }
    }, 25000);
  }

  function boot() {
    loadSkin();
    applyViewMode(state.view);
    bindEvents();
    refreshAll();
    initAutoRefresh();
  }

  boot();
})();
