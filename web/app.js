(() => {
  const state = {
    allLeads: [],
    leads: [],
    selectedNoteId: "",
    loading: false,
    skin: "business-blue",
    search: "",
    view: "overview",
    runItems: [],
  };

  const dom = {
    kpiRaw: document.getElementById("kpiRaw"),
    kpiSummary: document.getElementById("kpiSummary"),
    kpiJobs: document.getElementById("kpiJobs"),
    kpiSend: document.getElementById("kpiSend"),
    latestRunId: document.getElementById("latestRunId"),
    latestRunTime: document.getElementById("latestRunTime"),
    digestMinutes: document.getElementById("digestMinutes"),
    leadCount: document.getElementById("leadCount"),
    leadBody: document.getElementById("leadBody"),
    detailBox: document.getElementById("detailBox"),
    runList: document.getElementById("runList"),
    searchInput: document.getElementById("searchInput"),
    refreshBtn: document.getElementById("refreshBtn"),
    skinBtn: document.getElementById("skinBtn"),
    navItems: document.querySelectorAll(".nav-item[data-view]"),
    workspace: document.getElementById("workspace"),
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

  function fmtTime(value) {
    const text = String(value ?? "").trim();
    if (!text) {
      return "-";
    }
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
    if (!Number.isFinite(n)) {
      return "0";
    }
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
    const title = `热度分: ${score}`;
    return `<span class=\"badge ${cls}\" title=\"${escapeHtml(title)}\">${escapeHtml(toText(status))}</span>`;
  }

  function buildApiUrl(path, base) {
    if (!base) {
      return path;
    }
    return `${base}${path}`;
  }

  async function fetchJson(path) {
    let lastError = null;
    for (const base of API_BASES) {
      const url = buildApiUrl(path, base);
      try {
        const resp = await fetch(url, {
          headers: { "Accept": "application/json" },
          cache: "no-store",
        });
        if (!resp.ok) {
          throw new Error(`${resp.status} ${resp.statusText}`);
        }
        return await resp.json();
      } catch (err) {
        lastError = err;
      }
    }

    const reason = lastError instanceof Error ? lastError.message : String(lastError || "unknown error");
    throw new Error(`API unavailable (${reason}). 请启动 dashboard: http://127.0.0.1:8787`);
  }

  function renderSummary(summary) {
    dom.kpiRaw.textContent = fmtInt(summary.raw_count);
    dom.kpiSummary.textContent = fmtInt(summary.summary_count);
    dom.kpiJobs.textContent = fmtInt(summary.jobs_count);
    dom.kpiSend.textContent = fmtInt(summary.send_count);

    dom.latestRunId.textContent = toText(summary.latest_run_id);
    dom.latestRunTime.textContent = fmtTime(summary.latest_run_time);
    dom.digestMinutes.textContent = fmtInt(summary.digest_interval_minutes || 60);
  }

  function renderRuns(items) {
    state.runItems = Array.isArray(items) ? items : [];
    if (!state.runItems.length) {
      dom.runList.innerHTML = "<li>暂无运行记录</li>";
      return;
    }

    const html = state.runItems
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
    dom.runList.innerHTML = html;
  }

  function getSelectedLead() {
    if (!state.leads.length) {
      return null;
    }
    const byId = state.leads.find((x) => x.note_id === state.selectedNoteId);
    if (byId) {
      return byId;
    }
    state.selectedNoteId = state.leads[0].note_id;
    return state.leads[0];
  }

  function leadsForView(items) {
    const list = Array.isArray(items) ? items : [];
    if (state.view === "summary") {
      return list.filter((item) => String(item.summary || "").trim());
    }
    if (state.view === "sendlog") {
      return list.slice(0, 80);
    }
    return list;
  }

  function applyViewMode(nextView) {
    const allowed = new Set(["overview", "leads", "summary", "sendlog"]);
    state.view = allowed.has(nextView) ? nextView : "overview";
    document.body.dataset.view = state.view;

    dom.navItems.forEach((item) => {
      const active = item.getAttribute("data-view") === state.view;
      item.classList.toggle("active", active);
    });

    if (state.view === "summary") {
      dom.searchInput.placeholder = "按摘要 / 岗位 / 公司筛选";
    } else if (state.view === "sendlog") {
      dom.searchInput.placeholder = "按运行记录关联线索筛选";
    } else {
      dom.searchInput.placeholder = "公司 / 岗位 / 地点 / 摘要";
    }

    renderLeads(leadsForView(state.allLeads));
    if (dom.workspace) {
      dom.workspace.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function compactText(value, limit = 1600) {
    const text = String(value ?? "").trim();
    if (!text) {
      return "";
    }
    if (text.length <= limit) {
      return text;
    }
    return `${text.slice(0, limit)}\n...（已截断，共 ${text.length} 字）`;
  }

  function renderDetail(lead) {
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
    const req = compactText(lead.requirements, 800) || "暂无";
    const summary = compactText(lead.summary, 3000) || "暂无摘要";
    const comments = compactText(lead.comments_preview, 1200) || "暂无评论预览";
    const detailText = compactText(lead.detail_text, 2000) || "暂无正文详情";
    const risk = compactText(lead.risk_flags, 280) || "无";
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

      <div class="detail-block">
        <h5>结构化要求</h5>
        <pre>${escapeHtml(req)}</pre>
      </div>

      <div class="detail-block">
        <h5>摘要</h5>
        <pre>${escapeHtml(summary)}</pre>
      </div>

      <div class="detail-block">
        <h5>评论预览</h5>
        <pre>${escapeHtml(comments)}</pre>
      </div>

      <div class="detail-block">
        <h5>原帖正文详情</h5>
        <pre>${escapeHtml(detailText)}</pre>
      </div>

      <div class="meta-line">风险标签：${escapeHtml(risk)}</div>
      ${url ? `<div class=\"detail-link\"><a href=\"${escapeHtml(url)}\" target=\"_blank\" rel=\"noreferrer\">打开原帖链接</a></div>` : ""}
    `;
  }

  function renderLeads(items) {
    state.leads = Array.isArray(items) ? items : [];
    dom.leadCount.textContent = `${state.leads.length} 条`;

    if (!state.leads.length) {
      dom.leadBody.innerHTML = "<tr><td colspan=\"5\" class=\"table-tip\">暂无匹配线索</td></tr>";
      state.selectedNoteId = "";
      renderDetail(null);
      return;
    }

    if (!state.selectedNoteId || !state.leads.some((x) => x.note_id === state.selectedNoteId)) {
      state.selectedNoteId = state.leads[0].note_id;
    }

    const rowsHtml = state.leads
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

    dom.leadBody.innerHTML = rowsHtml;
    bindLeadRowClick();
    renderDetail(getSelectedLead());
  }

  function bindLeadRowClick() {
    const rows = dom.leadBody.querySelectorAll("tr[data-id]");
    rows.forEach((row) => {
      row.addEventListener("click", () => {
        state.selectedNoteId = row.getAttribute("data-id") || "";
        renderLeads(state.leads);
      });
    });
  }

  function setLoadingTable(message = "加载中...") {
    dom.leadBody.innerHTML = `<tr><td colspan=\"5\" class=\"table-tip\">${escapeHtml(message)}</td></tr>`;
  }

  function setTableError(message) {
    dom.leadBody.innerHTML = `<tr><td colspan=\"5\" class=\"table-tip error\">${escapeHtml(message)}</td></tr>`;
  }

  async function loadSummaryAndRuns() {
    const [summary, runsResp] = await Promise.all([
      fetchJson("/api/summary"),
      fetchJson("/api/runs?limit=10"),
    ]);
    renderSummary(summary || {});
    renderRuns((runsResp && runsResp.items) || []);
  }

  async function loadLeads() {
    const q = state.search.trim();
    const query = new URLSearchParams();
    query.set("limit", "300");
    if (q) {
      query.set("q", q);
    }
    const resp = await fetchJson(`/api/leads?${query.toString()}`);
    state.allLeads = (resp && resp.items) || [];
    renderLeads(leadsForView(state.allLeads));
  }

  async function refreshAll() {
    if (state.loading) {
      return;
    }
    state.loading = true;
    dom.refreshBtn.disabled = true;
    setLoadingTable("正在加载实时数据...");

    try {
      await loadSummaryAndRuns();
      await loadLeads();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setTableError(`加载失败：${msg}`);
      dom.detailBox.innerHTML = `<h4>数据加载异常</h4><p>${escapeHtml(msg)}</p>`;
    } finally {
      state.loading = false;
      dom.refreshBtn.disabled = false;
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
      if (timer) {
        clearTimeout(timer);
      }
      timer = setTimeout(() => fn(...args), wait);
    };
  }

  function bindEvents() {
    dom.refreshBtn.addEventListener("click", () => {
      refreshAll();
    });

    dom.skinBtn.addEventListener("click", () => {
      toggleSkin();
    });

    dom.searchInput.addEventListener(
      "input",
      debounce((event) => {
        state.search = String(event.target.value || "");
        loadLeads().catch((err) => {
          const msg = err instanceof Error ? err.message : String(err);
          setTableError(`搜索失败：${msg}`);
        });
      }, 260),
    );

    dom.navItems.forEach((item) => {
      item.addEventListener("click", () => {
        applyViewMode(item.getAttribute("data-view") || "overview");
      });
    });
  }

  function initAutoRefresh() {
    setInterval(() => {
      loadSummaryAndRuns().catch(() => {
        // Passive refresh failure should not break UX.
      });
    }, 30000);
  }

  function boot() {
    loadSkin();
    applyViewMode("overview");
    bindEvents();
    refreshAll();
    initAutoRefresh();
  }

  boot();
})();
