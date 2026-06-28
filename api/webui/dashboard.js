const state = {
  tasks: [],
  selectedId: "",
  dryRunCommand: "",
  counts: {},
  files: [],
  logs: [],
  crawlerLogs: [],
  pipelineLogs: [],
  runner: null,
  crawlerStatus: null,
  analysisReport: null,
  lastDryRunTaskId: "",
  lastDryRunFilePath: "",
};

const $ = (id) => document.getElementById(id);
const platformLogos = {
  "抖音": "/logos/douyin.png",
  "小红书": "/logos/xiaohongshu_logo.png",
  "哔哩哔哩": "/logos/bilibili_logo.png",
  "Bilibili": "/logos/bilibili_logo.png",
};
const statusClass = {
  "待执行": "pending",
  "运行中": "running",
  "执行中": "running",
  "已完成": "done",
  "部分失败": "failed",
  "失败": "failed",
  "已取消": "failed",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.message || `${res.status} ${res.statusText}`);
  return data;
}

let pipelinePollTimer = null;

async function loadEnv() {
  // Merged into loadConfig() — environment checks now live in Settings → 配置检查
  return loadConfig();
}

async function loadConfig() {
  const [base, webhook, platforms, options] = await Promise.all([
    api("/api/env/check").catch((error) => ({ success: false, message: error.message })),
    api("/api/feishu/webhook/status").catch(() => ({ configured: false })),
    api("/api/config/platforms").catch(() => ({ platforms: [] })),
    api("/api/config/options").catch(() => ({ login_types: [], crawler_types: [], save_options: [] })),
  ]);
  const items = [
    { label: "Python 运行环境", value: base.success ? "正常" : (base.message || "异常"), ok: Boolean(base.success) },
    { label: "网络连接", value: "正常", ok: true },
    { label: "Webhook 通知", value: webhook.configured ? "已配置" : "未配置", ok: Boolean(webhook.configured) },
    { label: "支持平台", value: `${platforms.platforms?.length || 0} 个`, ok: true },
    { label: "保存格式", value: `${options.save_options?.length || 0} 种`, ok: true },
  ];
  $("configGrid").innerHTML = items.map((item) => `
    <div class="config-item ${item.ok ? "ok" : "bad"}">
      <span>${escapeHtml(item.label)}</span>
      <strong>${escapeHtml(item.value)}</strong>
    </div>
  `).join("");
}

async function loadTasks() {
  try {
    const data = await api("/api/tasks");
    state.tasks = data.tasks || [];
    state.counts = data.counts || {};
    if (!state.selectedId && state.tasks.length) state.selectedId = state.tasks[0].id;
    if (state.selectedId && !state.tasks.some((task) => String(task.id) === state.selectedId)) {
      state.selectedId = state.tasks[0]?.id || "";
    }
    renderTasks();
    renderDetails();
  } catch (error) {
    state.tasks = [];
    $("taskRows").innerHTML = `<tr><td colspan="7" class="empty">读取任务失败：${escapeHtml(error.message)}</td></tr>`;
    $("taskTotal").textContent = "（共 0 条）";
    appendLocalLog("error", `读取任务失败：${error.message}`);
  }
}

function renderTasks() {
  $("countPending").textContent = state.counts["待执行"] || 0;
  $("countRunning").textContent = (state.counts["运行中"] || 0) + (state.counts["执行中"] || 0);
  $("countDone").textContent = state.counts["已完成"] || 0;
  $("countFailed").textContent = (state.counts["失败"] || 0) + (state.counts["部分失败"] || 0) + (state.counts["已取消"] || 0);
  $("taskTotal").textContent = `（共 ${state.tasks.length} 条）`;

  if (!state.tasks.length) {
    $("taskRows").innerHTML = '<tr><td colspan="7" class="empty">暂无任务，点击"新建任务"写入一条。</td></tr>';
    return;
  }

  $("taskRows").innerHTML = state.tasks.map((task) => {
    const f = task;
    const platform = f.platform || f.crawler_type || "-";
    const logo = platformLogos[platform];
    const logoHtml = logo
      ? `<img class="platform-logo" src="${logo}" alt="">`
      : `<span class="platform-fallback">${escapeHtml(String(platform).slice(0, 1))}</span>`;
    const status = f.status || "未设置";
    return `
      <tr class="${String(task.id) === state.selectedId ? "selected" : ""}" data-id="${escapeHtml(task.id)}">
        <td><span class="platform-cell">${logoHtml}${escapeHtml(platform)}</span></td>
        <td>${escapeHtml(f.crawler_type || "-")}</td>
        <td>${escapeHtml(f.keywords || f.specified_id || f.creator_id || "-")}</td>
        <td>${escapeHtml(f.max_notes_count || f.max_notes_count || "-")}</td>
        <td><span class="badge ${statusClass[status] || ""}">${escapeHtml(status)}</span></td>
        <td>${escapeHtml(f.finished_at || f.created_at || "-")}</td>
        <td><div class="row-actions"><button data-select-task="${escapeHtml(task.id)}">选择</button></div></td>
      </tr>`;
  }).join("");
}

function selectedTask() {
  return state.tasks.find((task) => String(task.id) === state.selectedId) || state.tasks[0] || null;
}

function renderDetails() {
  const task = selectedTask();
  if (!task) {
    $("taskDetails").innerHTML = "<dt>状态</dt><dd>暂无任务</dd>";
    $("commandBox").textContent = "请选择一条采集任务。";
    $("selectedTaskStatus").textContent = "未选择";
    return;
  }
  const f = task;
  const rows = [
    ["平台", f.platform || "-"],
    ["采集类型", f.crawler_type || "-"],
    ["关键词", f.keywords || f.specified_id || f.creator_id || "-"],
    ["最大数量", f.max_notes_count || "-"],
    ["状态", f.status || "-"],
    ["开始时间", f.created_at || "-"],
    ["完成时间", f.finished_at || "-"],
    ["成功条数", f.success_count || "0"],
    ["跳过条数", f.skip_count || "0"],
    ["失败条数", f.fail_count || "0"],
  ];
  $("taskDetails").innerHTML = rows.map(([key, value]) => `<dt>${key}</dt><dd>${escapeHtml(value || "-")}</dd>`).join("");
  $("selectedTaskStatus").textContent = f.status || "未设置";
  $("commandBox").textContent = state.dryRunCommand || task.error || task.command || "这条任务缺少可预览命令。";
}

async function startRunner(dryRun, taskId = state.selectedId) {
  if (!taskId) {
    appendLocalLog("error", "请先选择一个采集任务。");
    return;
  }
  setRunnerButtons(true);
  try {
    if (dryRun) {
      const data = await api(`/api/tasks/${taskId}/dry-run`, { method: "POST" });
      state.dryRunCommand = data.command || "无命令预览";
      appendLocalLog("info", "Dry-Run 命令预览：");
      document.getElementById("commandBox").textContent = state.dryRunCommand;
    } else {
      await api(`/api/tasks/${taskId}/start`, { method: "POST" });
      appendLocalLog("success", `任务已启动：${taskId}`);
    }
  } catch (error) {
    appendLocalLog("error", `操作失败：${error.message}`);
  } finally {
    setRunnerButtons(false);
    await loadTasks();
  }
}

async function stopRunner() {
  try {
    await api("/api/crawler/stop", { method: "POST" });
    appendLocalLog("warning", "已请求停止任务");
    await pollRunner();
  } catch (error) {
    appendLocalLog("error", `停止任务失败：${error.message}`);
  }
}

function setRunnerButtons(disabled) {
  $("dryRunBtn").disabled = disabled;
  $("startBtn").disabled = disabled;
  $("stopRunnerBtn").disabled = disabled;
}

async function pollRunner() {
  const data = await api("/api/crawler/status");
  state.runner = data;
  renderLogs();
  if (data.running) setTimeout(pollRunner, 1200);
}

async function loadCrawlerStatus() {
  const data = await api("/api/crawler/status").catch((error) => ({ status: "error", error_message: error.message }));
  state.crawlerStatus = data;
  $("crawlerStatusText").textContent = `状态：${crawlerStatusText(data.status)}`;
}

async function startCrawler() {
  const payload = crawlerPayload();
  const validation = validateCrawlerPayload(payload);
  if (validation) {
    appendLocalLog("error", validation);
    return;
  }
  if (!window.confirm("将正式启动本机采集任务。请确认只采集公开内容，并已遵守目标平台规则。")) {
    return;
  }
  clearAllLogs();
  try {
    const { confirm_public: _confirmPublic, ...requestPayload } = payload;
    await api("/api/crawler/start", { method: "POST", body: JSON.stringify(requestPayload) });
    appendLocalLog("success", `本机采集已启动：${payload.platform} / ${payload.crawler_type}`);
    await loadCrawlerStatus();
    await loadLogs();
  } catch (error) {
    appendLocalLog("error", `本机采集启动失败：${error.message}`);
  }
}

async function stopCrawler() {
  try {
    await api("/api/crawler/stop", { method: "POST" });
    appendLocalLog("warning", "已请求停止本机采集");
    await loadCrawlerStatus();
    await loadLogs();
  } catch (error) {
    appendLocalLog("error", `停止本机采集失败：${error.message}`);
  }
}

function crawlerPayload() {
  const form = new FormData($("crawlerForm"));
  const maxNotes = numberOrNull(form.get("max_notes_count"));
  const maxComments = numberOrNull(form.get("max_comments_count"));
  return {
    platform: form.get("platform"),
    login_type: form.get("login_type"),
    crawler_type: form.get("crawler_type"),
    industry_type: form.get("industry_type"),
    keywords: String(form.get("keywords") || "").trim(),
    specified_ids: String(form.get("specified_ids") || "").trim(),
    creator_ids: String(form.get("creator_ids") || "").trim(),
    start_page: Number(form.get("start_page") || 1),
    enable_comments: form.get("enable_comments") === "on",
    enable_sub_comments: form.get("enable_sub_comments") === "on",
    save_option: form.get("save_option"),
    headless: form.get("headless") === "on",
    max_notes_count: maxNotes,
    max_comments_count: maxComments,
    confirm_public: form.get("confirm_public") === "on",
  };
}

function validateCrawlerPayload(payload) {
  if (payload.crawler_type === "search" && !payload.keywords) return "关键词采集需要填写关键词。";
  if (payload.crawler_type === "detail" && !payload.specified_ids) return "指定ID采集需要填写指定ID。";
  if (payload.crawler_type === "creator" && !payload.creator_ids) return "创作者采集需要填写创作者ID。";
  if (!payload.confirm_public) return "启动采集前，请勾选公开内容合规确认。";
  return "";
}

function updateCrawlerPreview() {
  const payload = crawlerPayload();
  updateCrawlerModeFields(payload.crawler_type);
  $("crawlerPayloadPreview").textContent = JSON.stringify(payload, null, 2);
}

function updateCrawlerModeFields(mode) {
  document.querySelectorAll(".mode-field").forEach((item) => {
    item.classList.toggle("hidden", item.dataset.mode !== mode);
  });
}

async function loadDataFiles() {
  const [stats, files] = await Promise.all([
    api("/api/data/stats").catch(() => ({ total_files: 0, total_size: 0 })),
    api("/api/data/files").catch((error) => ({ files: [], error: error.message })),
  ]);
  state.files = files.files || [];
  $("dataStatsText").textContent = `文件：${stats.total_files || 0}，大小：${formatBytes(stats.total_size || 0)}`;
  renderDataFiles();
}

function renderDataFiles() {
  if (!state.files.length) {
    $("dataFileRows").innerHTML = '<tr><td colspan="6" class="empty">暂无可管理的导出文件。采集完成后这里会出现 JSONL/CSV/SQLite 等文件。</td></tr>';
    return;
  }
  $("dataFileRows").innerHTML = state.files.map((file) => {
      const safePath = escapeHtml(file.path);
      const urlPath = filePathForUrl(file.path);
      return `
      <tr data-path="${safePath}">
        <td>${escapeHtml(file.path)}</td>
        <td>${escapeHtml(file.type || "-")}</td>
        <td>${escapeHtml(file.record_count ?? "-")}</td>
        <td>${formatBytes(file.size || 0)}</td>
        <td>${formatDate(file.modified_at)}</td>
        <td>
          <div class="file-actions">
            <button data-file-action="preview" data-path="${safePath}">预览</button>
            <button data-file-action="report" data-path="${safePath}">分析报告</button>
            <a href="/api/data/download/${urlPath}" target="_blank" rel="noreferrer">下载</a>
          </div>
        </td>
      </tr>`;
  }).join("");
}

function summarizeRecord(record) {
  if (!record || typeof record !== "object") return "-";
  const parts = [
    record.title,
    record.desc,
    record.content,
    record.text,
  ].filter(Boolean);
  return parts.join(" ").replace(/\s+/g, " ").slice(0, 120) || "-";
}

function solutionTextForCategory(category, solutions) {
  const matched = solutions.find((item) => {
    const name = item.category || item.category_name || item.name || "";
    return String(name) === String(category);
  });
  if (!matched) return "-";
  const list = matched.solutions || [];
  if (Array.isArray(list) && list.length) {
    return list.map((item) => {
      const name = item.name || item.solution_name || "";
      const ptype = item.product_type || item.solution_type || "";
      const cost = item.cost || "";
      let parts = [name];
      if (ptype) parts.push(ptype);
      if (cost) parts.push(cost + "成本");
      return parts.join(" / ");
    }).join("  |  ").slice(0, 180);
  }
  return "-";
}

// ── AI需求机会分析报告 v3 ────────────────────────────────────────
function normalizeReportRows(report) {
  if (!report) return [];
  const aggregation = Array.isArray(report.aggregation) ? report.aggregation : [];
  const solutions = Array.isArray(report.solutions_data) ? report.solutions_data : [];
  var solMap = {};
  solutions.forEach(function(s) {
    var cat = s.category || "";
    solMap[cat] = (solMap[cat] || []).concat(s.solutions || []);
  });
  return aggregation.map(function(item, i) {
    var category = item.category || item.name || "未分类";
    var count = Number(item.count || item.total || 0);
    var hs = Number(item.hot_score || 0);
    var catSols = solMap[category] || [];
    var bestSol = catSols[0] || {};
    var productType = bestSol.product_type || bestSol.solution_type || "";
    var priority = i < 3 ? "P0" : i < 5 ? "P1" : "P2";
    return {
      category: category,
      count: count,
      hotScore: hs,
      priority: priority,
      productType: productType,
      solutionName: bestSol.name || bestSol.solution_name || "-",
      solutionSummary: bestSol.summary || "",
      mvpFeatures: (bestSol.core_features || []).slice(0, 3).join("、"),
      solutions: catSols,
    };
  });
}

// Color palette for product types
var PRODUCT_COLORS = ["#3b72ff", "#16a06a", "#7c4dff", "#f5a524", "#f04438", "#0891b2", "#9333ea", "#db2777"];

function renderAnalysisReport(report) {
  if (report === undefined) report = state.analysisReport;
  var hasReport = Boolean(report && report.total > 0);

  // KPI cards
  var el;
  var agg = report && report.aggregation ? report.aggregation : [];
  var total = report ? (report.total || 0) : 0;
  var classifiedCount = report ? (report.classified_count || 0) : 0;
  var solutionsCount = report ? (report.solutions || 0) : 0;
  var hotCount = agg.filter(function(a) { return (a.hot_score || 0) >= 2; }).length;
  el = document.getElementById('arReportTotal'); if(el) el.textContent = hasReport ? String(total) : '0';
  el = document.getElementById('arReportNote'); if(el) el.textContent = hasReport ? '有效 ' + classifiedCount + ' / 已分类 ' + agg.length : '暂无数据';
  el = document.getElementById('arReportCategories'); if(el) el.textContent = hasReport ? String(agg.length) : '0';
  el = document.getElementById('arClassifiedNote'); if(el) el.textContent = hasReport ? '已聚类需求簇' : '未分类';
  el = document.getElementById('arHotCount'); if(el) el.textContent = hasReport ? String(hotCount) : '0';
  el = document.getElementById('arReportSolutions'); if(el) el.textContent = hasReport ? String(solutionsCount) : '0';
  el = document.getElementById('arTopOpps'); if(el) el.textContent = hasReport ? String(Math.min(3, agg.length)) : '0';
  el = document.getElementById('arWebhookStatus'); if(el) el.textContent = hasReport && report.webhook_sent ? '已发送' : '未发送';
  el = document.getElementById('arGeneratedAt'); if(el) el.textContent = report && report.generated_at ? report.generated_at : '飞书通知';

  // Show/hide sections
  var sections = document.querySelectorAll('#arOpportunitySection, #arTableSection');
  var emptyGuide = document.getElementById('arEmptyGuide');
  sections.forEach(function(s) { s.style.display = hasReport ? '' : 'none'; });
  if (emptyGuide) emptyGuide.style.display = hasReport ? 'none' : '';

  if (!hasReport) {
    document.getElementById('arSummaryText').textContent = '暂无分析数据。请在"需求库"中选择数据文件并点击"分析报告"生成报告，或等待采集完成后自动生成。';
    document.getElementById('arNextSteps').innerHTML = '<div class="ar-mini-item"><span class="ar-rank">1</span><div><b>采集数据</b><p>在"数据采集"页面新建任务，选择平台和关键词。</p></div></div><div class="ar-mini-item"><span class="ar-rank">2</span><div><b>生成分析报告</b><p>采集完成后在"需求库"中点击分析报告按钮。</p></div></div><div class="ar-mini-item"><span class="ar-rank">3</span><div><b>查看结果</b><p>报告自动推送到此页面和飞书群。</p></div></div>';
    document.getElementById('arBarChart').innerHTML = '<div class="ar-bar-row"><span class="ar-bar-name">暂无数据</span><div class="ar-bar-track"><div class="ar-bar-fill" style="width:100%"></div></div><span class="ar-bar-value">—</span></div>';
    return;
  }

  // AI Summary
  var top3Names = agg.slice(0, 3).map(function(a) { return a.category; });
  var summaryText = "本批数据中，用户最集中关注" + (top3Names.length ? "「" + top3Names.join("」「") + "」" : "各个") + "方向。";
  if (top3Names.length >= 2) summaryText += "优先建议围绕" + top3Names[0] + "和" + top3Names[1] + "开发产品方案。";
  summaryText += "详细分类和AI产品建议见下方表格。";
  document.getElementById('arSummaryText').textContent = summaryText;

  var tagHtml = top3Names.map(function(n) { return '<span class="ar-tag ar-p0">核心：' + escapeHtml(n) + '</span>'; }).join('');
  tagHtml += '<span class="ar-tag ar-ai">AI可解决度高</span>';
  document.getElementById('arTagRow').innerHTML = tagHtml;

  // Next steps
  document.getElementById('arNextSteps').innerHTML =
    '<div class="ar-mini-item"><span class="ar-rank">1</span><div><b>先做"' + escapeHtml(top3Names[0] || '未知') + '"方案</b><p>高频且AI可解决，验证核心功能即可。</p></div></div>' +
    '<div class="ar-mini-item"><span class="ar-rank">2</span><div><b>补充代表评论证据链</b><p>每个需求簇保留5-10条原始内容，提升报告可信度。</p></div></div>' +
    '<div class="ar-mini-item"><span class="ar-rank">3</span><div><b>导出到飞书/企微</b><p>把Top 3机会推送到群聊供团队讨论。</p></div></div>';

  // Charts
  renderBarChart(agg);
  renderDonutChart(report);
  renderQuadChart(agg);

  // Opportunity cards
  var oppHtml = '';
  var rows = normalizeReportRows(report);
  rows.slice(0, 6).forEach(function(r) {
    oppHtml += '<div class="ar-opp-card"><div class="ar-opp-head"><h3>' + escapeHtml(r.category) + '</h3><span class="ar-prior ar-p0">' + escapeHtml(r.priority) + '</span></div>';
    oppHtml += '<p class="ar-opp-desc">' + escapeHtml(r.solutionSummary || (r.count + '次提及，热度' + r.hotScore)) + '</p>';
    if (r.mvpFeatures) oppHtml += '<ul class="ar-opp-list">' + r.mvpFeatures.split('、').map(function(f) { return '<li>' + escapeHtml(f) + '</li>'; }).join('') + '</ul>';
    oppHtml += '</div>';
  });
  document.getElementById('arOpportunityGrid').innerHTML = oppHtml || '<p>暂无方案详情</p>';

  // Detail table
  renderReportTable(rows);

  // Bind tabs
  bindArTabs();
  bindArSidebar();
  bindArDrawer();
}

function renderBarChart(agg) {
  var maxCount = agg.length ? Math.max.apply(null, agg.map(function(a) { return a.count || 0; })) : 1;
  var html = '';
  agg.slice(0, 8).forEach(function(item) {
    var pct = Math.round(((item.count || 0) / maxCount) * 100);
    html += '<div class="ar-bar-row"><span class="ar-bar-name">' + escapeHtml(item.category) + '</span><div class="ar-bar-track"><div class="ar-bar-fill" style="width:' + pct + '%"></div></div><span class="ar-bar-value">' + (item.count || 0) + '</span></div>';
  });
  if (!html) html = '<div class="ar-bar-row"><span class="ar-bar-name">暂无数据</span><div class="ar-bar-track"><div class="ar-bar-fill" style="width:100%"></div></div><span class="ar-bar-value">—</span></div>';
  document.getElementById('arBarChart').innerHTML = html;
}

function renderDonutChart(report) {
  var solutions = report && report.solutions_data ? report.solutions_data : [];
  var typeCount = {};
  solutions.forEach(function(s) {
    (s.solutions || []).forEach(function(sol) {
      var t = sol.product_type || sol.solution_type || "其他";
      typeCount[t] = (typeCount[t] || 0) + 1;
    });
  });
  var entries = Object.keys(typeCount);
  if (!entries.length) {
    document.getElementById('arDonut').style.background = '#edf2fa';
    document.getElementById('arLegend').innerHTML = '<div class="ar-legend-item"><span>暂无数据</span><b>—</b></div>';
    return;
  }
  var total = entries.reduce(function(s, k) { return s + typeCount[k]; }, 0);
  var cumulative = 0;
  var segments = entries.map(function(k, i) {
    var pct = typeCount[k] / total;
    var start = cumulative;
    cumulative += pct;
    return { name: k, count: typeCount[k], start: start, end: cumulative, color: PRODUCT_COLORS[i % PRODUCT_COLORS.length] };
  });
  var donutStr = segments.map(function(s) {
    return s.color + ' ' + (s.start * 100).toFixed(0) + '% ' + (s.end * 100).toFixed(0) + '%';
  }).join(', ');
  document.getElementById('arDonut').style.background = 'conic-gradient(' + donutStr + ')';
  document.getElementById('arLegend').innerHTML = segments.map(function(s) {
    return '<div class="ar-legend-item"><span><i class="ar-dot" style="background:' + s.color + '"></i>' + escapeHtml(s.name) + '</span><b>' + s.count + '</b></div>';
  }).join('');
}

function renderQuadChart(agg) {
  var html = '<div class="ar-quad-label">高热度 × 高频次</div>';
  if (!agg.length) { document.getElementById('arQuad').innerHTML = html; return; }
  var maxCount = Math.max.apply(null, agg.map(function(a) { return a.count || 0; }));
  var maxHot = Math.max.apply(null, agg.map(function(a) { return a.hot_score || 0; }));
  maxHot = maxHot || 1; maxCount = maxCount || 1;
  agg.slice(0, 12).forEach(function(item) {
    var left = Math.min(92, ((item.count || 0) / maxCount) * 92);
    var top = Math.min(92, 92 - ((item.hot_score || 0) / maxHot) * 92);
    var c = item.hot_score > (maxHot * 0.6) && item.count > (maxCount * 0.5) ? 'rgba(22,160,106,.85)' : 'rgba(59,114,255,.85)';
    html += '<span class="ar-bubble" style="left:' + left + '%;top:' + top + '%;background:' + c + '" title="' + escapeHtml(item.category) + '"></span>';
  });
  document.getElementById('arQuad').innerHTML = html;
}

function renderReportTable(rows) {
  var html = '';
  rows.forEach(function(r, i) {
    html += '<tr data-cat="' + escapeHtml(r.category) + '" data-priority="' + r.priority + '" data-hot="' + (r.hotScore >= 2 ? 'hot' : '') + '">';
    html += '<td><span class="ar-prior ar-p0">' + escapeHtml(r.priority) + '</span></td>';
    html += '<td><b>' + escapeHtml(r.category) + '</b><br><small>' + escapeHtml(r.solutionSummary.substring(0, 30)) + '</small></td>';
    html += '<td>' + escapeHtml(r.category) + '</td>';
    html += '<td>' + r.count + '</td>';
    html += '<td><span class="ar-score">' + r.hotScore + '</span></td>';
    html += '<td>' + (r.productType ? '<span class="ar-product-pill">' + escapeHtml(r.productType) + '</span>' : '-') + '</td>';
    html += '<td>' + escapeHtml(r.solutionName) + '</td>';
    html += '<td><small>' + escapeHtml(r.mvpFeatures || '-') + '</small></td>';
    html += '<td><span class="ar-action-link ar-detail-link">查看详情</span></td>';
    html += '</tr>';
  });
  document.getElementById('arReportTable').innerHTML = html || '<tr><td colspan="9" class="empty">暂无明细数据</td></tr>';
}

function bindArTabs() {
  document.querySelectorAll('#arFilterTabs .ar-tab').forEach(function(tab) {
    tab.onclick = function() {
      document.querySelectorAll('#arFilterTabs .ar-tab').forEach(function(t) { t.classList.remove('active'); });
      tab.classList.add('active');
      var filter = tab.dataset.filter;
      document.querySelectorAll('#arReportTable tr').forEach(function(tr) {
        if (filter === 'all') { tr.style.display = ''; return; }
        if (filter === 'p0') tr.style.display = tr.dataset.priority === 'P0' ? '' : 'none';
        if (filter === 'hot') tr.style.display = tr.dataset.hot === 'hot' ? '' : 'none';
      });
    };
  });
}

function bindArSidebar() {
  document.querySelectorAll('#productTypeFilter .filter-btn').forEach(function(btn) {
    btn.onclick = function() {
      document.querySelectorAll('#productTypeFilter .filter-btn').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      var filter = btn.dataset.filter;
      document.querySelectorAll('#arReportTable tr').forEach(function(tr) {
        if (filter === 'all') { tr.style.display = ''; return; }
        var cat = tr.dataset.cat || '';
        tr.style.display = cat.indexOf(filter) >= 0 ? '' : 'none';
      });
    };
  });
}

function bindArDrawer() {
  document.querySelectorAll('.ar-detail-link').forEach(function(link) {
    link.onclick = function() {
      var tr = this.closest('tr');
      var cat = tr.dataset.cat || '';
      var report = state.analysisReport || {};
      var solutions = (report.solutions_data || []).filter(function(s) { return s.category === cat; });
      var classified = (report.classified_preview || report.classified_records || []).filter(function(r) {
        return (r.categories || []).indexOf(cat) >= 0;
      });

      document.getElementById('arDrawerTitle').textContent = cat || '需求详情';

      // Quotes
      var quotesHtml = '';
      classified.slice(0, 5).forEach(function(r) {
        var text = r.extracted_text || r.content || r.desc || '';
        var nickname = r.nickname || '';
        var likes = r.liked_count || r.like_count || 0;
        if (text) quotesHtml += '<div class="ar-quote">' + escapeHtml(text.substring(0, 150)) + (nickname ? ' — <b>' + escapeHtml(nickname) + '</b>' + (likes ? ' ❤' + likes : '') : '') + '</div>';
      });
      if (!quotesHtml) quotesHtml = '<p style="color:var(--muted)">暂无代表内容摘录</p>';
      document.getElementById('arDrawerQuotes').innerHTML = quotesHtml;

      // Keywords
      var kwHtml = '';
      var details = classified.length && classified[0].category_details ? classified[0].category_details : [];
      if (details.length && details[0].matched_keywords) {
        details[0].matched_keywords.forEach(function(kw) { kwHtml += '<span class="ar-tag ar-ai">' + escapeHtml(kw) + '</span>'; });
      }
      if (!kwHtml) kwHtml = '<span class="ar-tag">暂无关键词信息</span>';
      document.getElementById('arDrawerKeywords').innerHTML = kwHtml;

      // Solutions detail
      var solHtml = '';
      var allSols = [];
      solutions.forEach(function(s) { allSols = allSols.concat(s.solutions || []); });
      allSols.slice(0, 3).forEach(function(sol) {
        solHtml += '<div class="ar-mini-item" style="margin-bottom:8px"><span class="ar-rank">★</span><div><b>' + escapeHtml(sol.name || sol.solution_name || '方案') + '</b>';
        solHtml += '<p>' + escapeHtml(sol.summary || '') + '</p>';
        solHtml += '<div style="font-size:12px;color:var(--muted);margin-top:4px"><span class="ar-tag">' + escapeHtml(sol.product_type || sol.solution_type || '') + '</span> <span class="ar-tag">' + escapeHtml(sol.cost || '') + '成本</span></div></div></div>';
      });
      if (!solHtml) solHtml = '<p style="color:var(--muted)">暂无AI方案详情</p>';
      document.getElementById('arDrawerSolutions').innerHTML = solHtml;

      document.getElementById('arDrawer').classList.add('open');
      document.getElementById('arMask').classList.add('open');
    };
  });

  var closeBtn = document.getElementById('arCloseDrawer');
  var mask = document.getElementById('arMask');
  if (closeBtn) closeBtn.onclick = hideArDrawer;
  if (mask) mask.onclick = hideArDrawer;
}

function hideArDrawer() {
  document.getElementById('arDrawer').classList.remove('open');
  document.getElementById('arMask').classList.remove('open');
}

async function analyzeAndReport(filePath) {
  if (!window.confirm("将分析此文件并发送报告到飞书群：" + filePath + "\n确认继续？")) {
    return;
  }
  try {
    appendLocalLog("info", "正在分析数据...");
    var data = await api("/api/data/analyze-report", {
      method: "POST",
      body: JSON.stringify({ file_path: filePath, dry_run: false, batch_size: 100 }),
    });
    state.analysisReport = {
      total: data.total || 0,
      categories: data.categories || 0,
      aggregation: data.aggregation || [],
      classified_records: data.classified_records || [],
      classified_count: (data.classified_records || []).length,
      solutions: data.solutions || 0,
      solutions_data: data.solutions_data || [],
      webhook_sent: data.webhook_sent || false,
      generated_at: new Date().toLocaleString("zh-CN", { hour12: false }),
      file_path: filePath,
    };
    renderAnalysisReport();
    $("dataPreviewBox").textContent = JSON.stringify(data, null, 2);
    if (data.webhook_sent) {
      appendLocalLog("success", "分析完成：" + data.total + " 条数据，" + data.categories + " 个分类，已发送飞书群报告");
    } else {
      appendLocalLog("warning", "分析完成：" + data.total + " 条数据，" + data.categories + " 个分类，但 Webhook 未配置");
    }
    if (data.solutions > 0) {
      appendLocalLog("info", "AI 已为 " + data.solutions + " 个痛点生成解决方案");
    }
  } catch (error) {
    appendLocalLog("error", "分析失败：" + error.message);
  }
}

// Backward-compat: bind old filter sidebar if it exists
function bindOldReportFilters() {
  var oldFilter = document.getElementById('productTypeFilter');
  if (!oldFilter) return;
  oldFilter.querySelectorAll('.filter-btn').forEach(function(btn) {
    btn.onclick = function() {
      oldFilter.querySelectorAll('.filter-btn').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
      bindArSidebar();
    };
  });
}

async function previewDataFile(filePath) {
  try {
    const data = await api(`/api/data/files/${filePathForUrl(filePath)}?preview=true&limit=5`);
    $("dataPreviewBox").textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    $("dataPreviewBox").textContent = `预览失败：${error.message}`;
    appendLocalLog("error", `预览文件失败：${error.message}`);
  }
}

async function loadLogs() {
  const [runner, crawler] = await Promise.all([
    api("/api/crawler/status").catch(() => ({ logs: [] })),
    api("/api/crawler/logs?limit=160").catch(() => ({ logs: [] })),
  ]);
  state.runner = runner;
  state.crawlerLogs = crawler.logs || [];
  renderLogs();
}

function appendLocalLog(level, message) {
  state.logs.push({
    id: Date.now(),
    timestamp: new Date().toLocaleTimeString("zh-CN", { hour12: false }),
    level,
    message,
    source: "console",
  });
  state.logs = state.logs.slice(-160);
  renderLogs();
}

function clearAllLogs() {
  state.logs = [];
  state.crawlerLogs = [];
  state.pipelineLogs = [];
  if (state.runner) state.runner.logs = [];
  renderLogs();
  api("/api/crawler/logs/clear", { method: "POST" }).catch(() => {});
  api("/api/pipeline/logs/clear", { method: "POST" }).catch(() => {});
}

function normalizePipelineLog(line) {
  const text = String(line || "");
  const match = text.match(/^\[([^\]]+)\]\s*(.*)$/);
  const message = match ? match[2] : text;
  const lower = message.toLowerCase();
  let level = "info";
  if (lower.includes("failed") || lower.includes("error")) level = "error";
  else if (lower.includes("stderr") || lower.includes("warning") || lower.includes("timed out")) level = "warning";
  return {
    timestamp: match ? match[1] : "--",
    level,
    message,
    source: "pipeline",
  };
}

function renderLogs() {
  const logBox = $("logBox");
  const source = $("logSource").value;
  const onlyErrors = $("errorsOnly").checked;
  const feishuLogs = (state.runner?.logs || []).map((item) => ({ ...item, source: "feishu" }));
  const crawlerLogs = state.crawlerLogs.map((item) => ({ ...item, source: "crawler" }));
  let logs = [...state.logs, ...state.pipelineLogs, ...feishuLogs, ...crawlerLogs];
  if (source !== "all") logs = logs.filter((item) => item.source === source);
  if (onlyErrors) logs = logs.filter((item) => item.level === "error");
  if (!logs.length) {
    logBox.innerHTML = '<div class="log-line"><span>--</span><span class="info">INFO</span><span>等待任务运行...</span></div>';
    if ($("autoScroll").checked) requestAnimationFrame(() => { logBox.scrollTop = logBox.scrollHeight; });
    return;
  }
  logBox.innerHTML = logs.slice(-240).map((item) => `
    <div class="log-line">
      <span>${escapeHtml(item.timestamp || "--")}</span>
      <span class="${escapeHtml(item.level || "info")}">${escapeHtml(String(item.level || "info").toUpperCase())}</span>
      <span>${escapeHtml(item.message || "")}</span>
    </div>
  `).join("");
  if ($("autoScroll").checked) requestAnimationFrame(() => { logBox.scrollTop = logBox.scrollHeight; });
}

async function saveTask(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const body = {
    platform: form.get("platform"),
    crawler_type: form.get("crawler_type"),
    keywords: String(form.get("keywords") || "").trim(),
    specified_id: String(form.get("specified_id") || "").trim(),
    creator_id: String(form.get("creator_id") || "").trim(),
    max_notes_count: Number(form.get("max_notes_count") || 50),
    login_type: form.get("login_type"),
    enable_comments: form.get("enable_comments") === "on",
    enable_sub_comments: form.get("enable_sub_comments") === "on",
    status: form.get("status") || "待执行",
  };
  const taskId = String(form.get("record_id") || "").trim();
  try {
    const path = taskId ? `/api/tasks/${encodeURIComponent(taskId)}` : "/api/tasks";
    const method = taskId ? "PUT" : "POST";
    await api(path, { method, body: JSON.stringify(body) });
    $("taskDialog").close();
    appendLocalLog("success", `${taskId ? "已更新" : "已写入"}任务：${body.platform} / ${body.keywords || body.specified_id || body.creator_id}`);
    await loadTasks();
  } catch (error) {
    appendLocalLog("error", `保存任务失败：${error.message}`);
  }
}

function openTaskDialog(task = null) {
  const form = $("taskForm");
  form.reset();
  if (!task) {
    $("taskDialogTitle").textContent = "新建采集任务";
    form.elements.record_id.value = "";
    form.elements.status.value = "待执行";
    form.elements.max_notes_count.value = "50";
    form.elements.enable_comments.checked = true;
    form.elements.enable_sub_comments.checked = false;
    $("taskDialog").showModal();
    return;
  }
  const f = task;
  $("taskDialogTitle").textContent = "编辑采集任务";
  form.elements.record_id.value = task.id || "";
  setFormValue(form, "platform", f.platform || "微博");
  setFormValue(form, "crawler_type", f.crawler_type || "关键词");
  form.elements.keywords.value = f.keywords || "";
  form.elements.specified_id.value = f.specified_id || "";
  form.elements.creator_id.value = f.creator_id || "";
  form.elements.max_notes_count.value = f.max_notes_count || f.max_notes_count || 50;
  setFormValue(form, "login_type", f.login_type || "无需登录");
  setFormValue(form, "status", f.status || "待执行");
  form.elements.enable_comments.checked = f.enable_comments !== false;
  form.elements.enable_sub_comments.checked = f.enable_sub_comments === true;
  $("taskDialog").showModal();
}

function bindEvents() {
  const refreshAll = () => Promise.all([loadEnv(), loadConfig(), loadTasks(), loadLogs(), loadCrawlerStatus(), loadDataFiles(), loadWebhookStatus(), loadLlmConfig()]);
  $("refreshBtn").addEventListener("click", refreshAll);
  $("quickRefreshBtn").addEventListener("click", refreshAll);
  $("newTaskBtn").addEventListener("click", () => openTaskDialog());
  $("quickNewTaskBtn").addEventListener("click", () => openTaskDialog());
  $("editTaskBtn").addEventListener("click", () => openTaskDialog(selectedTask()));
  $("dryRunBtn").addEventListener("click", () => startRunner(true));
  $("quickDryRunBtn").addEventListener("click", () => startRunner(true));
  $("startBtn").addEventListener("click", () => startRunner(false));
  $("stopRunnerBtn").addEventListener("click", stopRunner);
  $("quickCrawlerBtn").addEventListener("click", () => document.querySelector("#crawlerSection")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  $("quickDataBtn").addEventListener("click", () => document.querySelector("#dataSection")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  $("copyCommandBtn").addEventListener("click", async () => {
    await navigator.clipboard.writeText($("commandBox").textContent);
    appendLocalLog("success", "命令预览已复制到剪贴板");
  });
  $("clearLogsBtn").addEventListener("click", () => {
    clearAllLogs();
  });
  $("clearAnalysisReportBtn")?.addEventListener("click", () => {
    state.analysisReport = null;
    renderAnalysisReport();
  });
  $("taskForm").addEventListener("submit", saveTask);
  $("closeTaskDialogBtn").addEventListener("click", () => $("taskDialog").close());
  $("taskRows").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-select-task]");
    if (button) {
      state.selectedId = button.dataset.selectTask;
      renderTasks();
      renderDetails();
      return;
    }
    const row = event.target.closest("tr[data-id]");
    if (row) {
      state.selectedId = row.dataset.id;
      renderTasks();
      renderDetails();
    }
  });
  $("startCrawlerBtn").addEventListener("click", startCrawler);
  $("stopCrawlerBtn").addEventListener("click", stopCrawler);
  $("refreshCrawlerBtn").addEventListener("click", loadCrawlerStatus);
  $("crawlerForm").addEventListener("input", updateCrawlerPreview);
  $("crawlerForm").addEventListener("change", updateCrawlerPreview);
  $("refreshDataBtn").addEventListener("click", loadDataFiles);
  $("dataFileRows").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-file-action]");
    if (!button) return;
    const path = button.dataset.path;
    if (button.dataset.fileAction === "preview") previewDataFile(path);
    if (button.dataset.fileAction === "report") analyzeAndReport(path);
  });
  $("refreshConfigBtn").addEventListener("click", () => Promise.all([loadEnv(), loadConfig()]));
  $("refreshConfigBtn").addEventListener("click", loadLlmConfig);
  $("saveWebhookBtn")?.addEventListener("click", saveWebhookUrl);
  $("testWebhookBtn")?.addEventListener("click", testWebhook);
  $("saveLlmBtn")?.addEventListener("click", saveLlmConfig);
  $("testLlmBtn")?.addEventListener("click", testLlmConnection);
  $("startPipelineBtn")?.addEventListener("click", startPipeline);
  $("refreshPipelineBtn")?.addEventListener("click", loadPipelineStatus);
  $("closeSolutionDialogBtn")?.addEventListener("click", function() { document.getElementById('solutionDialog').close(); });
  var solutionDialog = document.getElementById('solutionDialog');
  if (solutionDialog) {
    solutionDialog.addEventListener('click', function(ev) {
      if (ev.target === solutionDialog) solutionDialog.close();
    });
    solutionDialog.addEventListener('cancel', function(ev) { solutionDialog.close(); });
  }
  setupFilterButtons();
  ["logSource", "errorsOnly", "autoScroll"].forEach((id) => $(id).addEventListener("change", renderLogs));
  const workspace = document.querySelector(".workspace");
  const pageMap = {
    overview: "page-overview",
    data: "page-data",
    analysis: "page-analysis",
    settings: "page-settings",
  };
  const targetMap = {
    overview: "#pipelineSection",
    tasks: "#crawlerSection",
    logs: ".log-panel",
    data: "#dataSection",
    analysis: "#analysisReportSection",
    settings: "#configSection",
  };
  function scrollToTarget(selector) {
    const target = document.querySelector(selector);
    if (!target || !workspace) return;
    const top = workspace.scrollTop + target.getBoundingClientRect().top - workspace.getBoundingClientRect().top - 12;
    workspace.scrollTo({ top, behavior: "smooth" });
  }
  function showSection(section) {
    document.querySelectorAll(".page-panel").forEach((panel) => {
      panel.style.display = "none";
    });
    const page = document.getElementById(pageMap[section] || "page-overview");
    if (page) page.style.display = "block";
    scrollToTarget(targetMap[section] || "#crawlerSection");
  }
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      showSection(button.dataset.section);
    });
  });
  showSection("overview");
}

function setFormValue(form, name, value) {
  const field = form.elements[name];
  if (!field) return;
  const values = Array.from(field.options || []).map((option) => option.value);
  field.value = values.includes(String(value)) ? value : field.value;
}

function parseBoolField(value, fallback) {
  if (typeof value === "boolean") return value;
  const text = String(value ?? "").toLowerCase();
  if (!text) return fallback;
  return ["true", "1", "yes", "是", "开启", "启用"].includes(text);
}

function numberOrNull(value) {
  const text = String(value ?? "").trim();
  if (!text) return null;
  const number = Number(text);
  return Number.isFinite(number) ? number : null;
}

function filePathForUrl(filePath) {
  return String(filePath).replaceAll("\\", "/").split("/").map(encodeURIComponent).join("/");
}

function formatBytes(size) {
  if (!size) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let value = Number(size);
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(index ? 1 : 0)} ${units[index]}`;
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(Number(value) * 1000);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatTimeField(value) {
  if (!value) return "-";
  const text = String(value);
  if (/^\d{13}$/.test(text)) return new Date(Number(text)).toLocaleString("zh-CN", { hour12: false });
  if (/^\d{10}$/.test(text)) return new Date(Number(text) * 1000).toLocaleString("zh-CN", { hour12: false });
  return text;
}

function crawlerStatusText(status) {
  return {
    idle: "空闲",
    running: "运行中",
    stopping: "停止中",
    error: "异常",
  }[status] || status || "未知";
}


// ===== LLM AI Model Config =====

async function loadLlmConfig() {
  try {
    const data = await api("/api/llm/config");
    const statusEl = document.getElementById("llmStatus");
    if (!statusEl) return;
    if (data.configured) {
      statusEl.textContent = "状态：已配置";
      document.getElementById("llmApiKeyInput").value = data.LLM_API_KEY || "";
      document.getElementById("llmApiUrlInput").value = data.LLM_API_URL || "";
      document.getElementById("llmModelInput").value = data.LLM_MODEL || "";
    } else {
      statusEl.textContent = "状态：未配置";
    }
  } catch (error) {
    appendLocalLog("error", "读取 LLM 配置失败: " + error.message);
  }
}

async function saveLlmConfig() {
  const apiKey = document.getElementById("llmApiKeyInput").value.trim();
  const apiUrl = document.getElementById("llmApiUrlInput").value.trim();
  const model = document.getElementById("llmModelInput").value.trim();
  if (!apiKey) {
    appendLocalLog("warning", "API Key 不能为空");
    return;
  }
  try {
    await api("/api/llm/config", {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey, api_url: apiUrl, model: model }),
    });
    appendLocalLog("success", "LLM 配置已保存");
    await loadLlmConfig();
  } catch (error) {
    appendLocalLog("error", "保存 LLM 配置失败: " + error.message);
  }
}

async function testLlmConnection() {
  try {
    const result = await api("/api/llm/test", { method: "POST" });
    const statusEl = document.getElementById("llmStatus");
    if (result.success) {
      appendLocalLog("success", "LLM 连接测试成功");
      if (result.reply) {
        appendLocalLog("info", "模型回复: " + result.reply);
      }
      if (statusEl) {
        statusEl.textContent = "状态：已配置 ✅";
        statusEl.style.color = "var(--green)";
      }
    } else {
      appendLocalLog("error", "LLM 测试: " + (result.message || "失败"));
      if (statusEl) {
        statusEl.textContent = "状态：测试失败 ❌";
        statusEl.style.color = "var(--red)";
      }
    }
  } catch (error) {
    appendLocalLog("error", "LLM 测试失败: " + error.message);
  }
}

// ===== Feishu Webhook =====

async function loadWebhookStatus() {
  try {
    const data = await api("/api/feishu/webhook/status");
    const webhookStatusEl = document.getElementById("webhookStatus");
    if (!webhookStatusEl) return;
    if (data.configured) {
      webhookStatusEl.textContent = "状态：已配置 " + (data.url_masked ? "✅" : "");
      document.getElementById("webhookUrlInput").value = data.url || "";
    } else {
      webhookStatusEl.textContent = "状态：未配置";
    }
  } catch (error) {
    appendLocalLog("error", "读取Webhook状态失败：" + error.message);
  }
}

async function testWebhook() {
  try {
    const result = await api("/api/feishu/webhook/test", { method: "POST" });
    appendLocalLog("success", "Webhook 测试：" + (result.success ? "成功" : "失败"));
    return result;
  } catch (error) {
    appendLocalLog("error", "Webhook 测试失败：" + error.message);
  }
}

async function saveWebhookUrl() {
  const url = document.getElementById("webhookUrlInput").value.trim();
  if (!url) {
    appendLocalLog("warning", "Webhook URL 不能为空");
    return;
  }
  try {
    await api("/api/feishu/webhook/save", {
      method: "POST",
      body: JSON.stringify({ url: url }),
    });
    appendLocalLog("success", "Webhook URL 已保存");
    await loadWebhookStatus();
  } catch (error) {
    appendLocalLog("error", "保存Webhook失败：" + error.message);
  }
}





// ===== One-Click Pipeline =====

async function loadPipelineStatus() {
  try {
    const data = await api('/api/pipeline/status');
    const statusEl = document.getElementById('pipelineStatus');
    if (!statusEl) {return;}
    var map = { idle: '空闲', running: '运行中', completed: '已完成', failed: '失败' };
    statusEl.textContent = map[data.status] || data.status;
    state.pipelineLogs = (data.logs || []).map(normalizePipelineLog);
    renderLogs();
    if (data.last_result && data.last_result.total_files > 0) {
      document.getElementById('pipelineResult').innerHTML = '<div class="report-stat" style="display:inline-block;padding:12px 16px;border:1px solid var(--line);border-radius:8px;background:var(--surface-alt)"><span>采集文件</span><strong>' + data.last_result.total_files + '</strong></div>';
    }
    if (data.status === 'completed' && data.last_result && Array.isArray(data.last_result.analysis) && data.last_result.analysis.length > 0) {
      var analysisList = data.last_result.analysis;
      var mergedAgg = {};
      var mergedSolutions = [];
      var totalRecords = 0;
      var anyWebhookSent = false;
      for (var i = 0; i < analysisList.length; i++) {
        var a = analysisList[i];
        totalRecords += a.total || 0;
        if (a.webhook_sent) anyWebhookSent = true;
        if (Array.isArray(a.solutions_data)) mergedSolutions = mergedSolutions.concat(a.solutions_data);
        if (Array.isArray(a.aggregation)) {
          for (var j = 0; j < a.aggregation.length; j++) {
            var item = a.aggregation[j];
            var cat = item.category || item.name || '未分类';
            if (!mergedAgg[cat]) mergedAgg[cat] = { category: cat, count: 0 };
            mergedAgg[cat].count += Number(item.count || item.total || 0);
          }
        }
      }
      var aggArray = Object.values(mergedAgg).sort(function(x, y) { return y.count - x.count; });
      state.analysisReport = {
        total: totalRecords,
        categories: aggArray.length,
        aggregation: aggArray,
        classified_records: [],
        classified_count: totalRecords,
        solutions: mergedSolutions.length,
        solutions_data: mergedSolutions,
        webhook_sent: anyWebhookSent,
        generated_at: new Date().toLocaleString('zh-CN', { hour12: false }),
      };
      renderAnalysisReport();
    }
    if (data.status === 'running' && !pipelinePollTimer) {
      startPipelinePolling();
    }
    if (data.status === 'completed' || data.status === 'failed' || data.status === 'idle') {
      stopPipelinePolling();
    }
    return data;
  } catch(e) {}
}

function startPipelinePolling() {
  stopPipelinePolling();
  pipelinePollTimer = setInterval(loadPipelineStatus, 1500);
}

function stopPipelinePolling() {
  if (pipelinePollTimer) {
    clearInterval(pipelinePollTimer);
    pipelinePollTimer = null;
  }
}

async function startPipeline() {
  var platformInputs = document.querySelectorAll('#pipelinePlatforms input[type="checkbox"]:checked');
  var platforms = Array.from(platformInputs).map(function(input) { return input.value; });
  var keywordInput = document.querySelector('input[name="pipelineKeywordCount"]:checked');
  var keywordCount = parseInt(keywordInput ? keywordInput.value : '3') || 3;
  var maxNotes = parseInt(document.getElementById('pipelineMaxNotes').value) || 15;
  if (platforms.length === 0) { appendLocalLog('warning', '请选择平台'); return; }
  if (!confirm('启动自动需求发现\n平台: ' + platforms.join(', ') + '\n关键词数: ' + keywordCount)) {return;}
  clearAllLogs();
  try {
    appendLocalLog('info', '一键需求发现启动...');
    var data = await api('/api/pipeline/start', {
      method: 'POST',
      body: JSON.stringify({ platforms: platforms, keyword_count: keywordCount, max_notes: maxNotes }),
    });
    if (data.status === 'started') {
      appendLocalLog('success', data.message || '后台运行已启动');
      await loadPipelineStatus();
      startPipelinePolling();
    } else if (data.status === 'completed') {
      appendLocalLog('success', data.message || '完成');
      await loadPipelineStatus();
      loadDataFiles();
    } else {
      appendLocalLog('warning', data.message || '未启动');
    }
  } catch(e) {
    appendLocalLog('error', '失败: ' + e.message);
  }
}


// ===== Product Type Filter =====
var _filterType = 'all';

function setupFilterButtons() {
  var bar = document.getElementById('productTypeFilter');
  if (!bar) return;
  bar.addEventListener('click', function(e) {
    var btn = e.target.closest('.filter-btn');
    if (!btn) return;
    bar.querySelectorAll('.filter-btn').forEach(function(b) { b.classList.remove('active'); });
    btn.classList.add('active');
    _filterType = btn.dataset.filter;
    renderAnalysisReport();
  });
}

// ===== Solution Detail Dialog =====

function openSolutionDialog(category, solutions) {
  var matched = null;
  if (Array.isArray(solutions)) {
    for (var i = 0; i < solutions.length; i++) {
      if (solutions[i].category === category) { matched = solutions[i]; break; }
    }
  }
  var content = document.getElementById('solutionDetailContent');
  var titleEl = document.getElementById('solutionDialogTitle');
  if (!content) return;
  titleEl.textContent = category + ' - 方案详情';
  if (!matched || !matched.solutions || matched.solutions.length === 0) {
    content.innerHTML = '<p class="empty">暂无AI方案。</p>';
  } else {
    var html = '';
    for (var s = 0; s < matched.solutions.length; s++) {
      var sol = matched.solutions[s];
      var name = sol.name || sol.solution_name || '方案';
      var ptype = sol.product_type || sol.solution_type || '';
      var summary = sol.summary || '';
      var users = sol.target_users || '';
      var tech = sol.tech_stack || '';
      var cost = sol.cost || '';
      var timeline = sol.timeline || '';
      var monetization = sol.monetization || '';
      var reference = sol.reference || '';
      var innovation = sol.innovation || '';
      html += '<div class="solution-card">';
      html += '<div class="solution-card-head">';
      html += '<strong>' + escapeHtml(name) + '</strong>';
      if (ptype) html += '<span class="status-pill">' + escapeHtml(ptype) + '</span>';
      html += '</div>';
      if (summary) html += '<p class="solution-card-summary">' + escapeHtml(summary) + '</p>';
      html += '<dl>';
      if (users) html += '<dt>目标用户</dt><dd>' + escapeHtml(users) + '</dd>';
      if (tech) html += '<dt>技术栈</dt><dd>' + escapeHtml(tech) + '</dd>';
      if (cost) html += '<dt>开发成本</dt><dd>' + escapeHtml(cost) + '</dd>';
      if (timeline) html += '<dt>预估周期</dt><dd>' + escapeHtml(timeline) + '</dd>';
      if (monetization) html += '<dt>变现方式</dt><dd>' + escapeHtml(monetization) + '</dd>';
      if (reference) html += '<dt>竞品参考</dt><dd>' + escapeHtml(reference) + '</dd>';
      if (innovation) html += '<dt>创新点</dt><dd>' + escapeHtml(innovation) + '</dd>';
      html += '</dl>';
      html += '</div>';
    }
    content.innerHTML = html;
  }
  document.getElementById('solutionDialog').showModal();
}

function filterSolutions(solutions) {
  if (_filterType === 'all') return solutions;
  var result = [];
  for (var i = 0; i < solutions.length; i++) {
    var item = solutions[i];
    var sols = item.solutions || [];
    var filtered = [];
    for (var s = 0; s < sols.length; s++) {
      var ptype = sols[s].product_type || sols[s].solution_type || '';
      if (ptype.indexOf(_filterType) >= 0) { filtered.push(sols[s]); }
    }
    if (filtered.length > 0) {
      result.push({ category: item.category, count: item.count, rank: item.rank, solutions: filtered });
    }
  }
  return result;
}

// ── WebSocket: real-time log stream + analysis report push ──
function connectLogSocket() {
  var protocol = location.protocol === "https:" ? "wss" : "ws";
  var wsUrl = protocol + "://" + location.host + "/api/ws/logs";
  var ws = new WebSocket(wsUrl);
  ws.onopen = function () {
    appendLocalLog("info", "实时日志已连接");
  };
  ws.onmessage = function (event) {
    try {
      var msg = JSON.parse(event.data);
      // Check for analysis report push
      if (msg.type === "analysis_report" && msg.data) {
        state.analysisReport = {
          total: msg.data.total || 0,
          categories: msg.data.categories || 0,
          aggregation: msg.data.aggregation || [],
          classified_records: msg.data.classified_preview || [],
          classified_count: msg.data.classified_count || 0,
          solutions: msg.data.solutions || 0,
          solutions_data: msg.data.solutions_data || [],
          webhook_sent: msg.data.webhook_sent || false,
          generated_at: msg.data.generated_at || new Date().toLocaleString("zh-CN", { hour12: false }),
        };
        renderAnalysisReport();
        appendLocalLog("success", "新分析报告已接收：" + (msg.data.total || 0) + " 条数据，" + (msg.data.categories || 0) + " 个分类");
        return;
      }
      // Treat as log entry
      var entry = msg;
      if (entry.timestamp && entry.message != null) {
        state.crawlerLogs.push(entry);
        state.crawlerLogs = state.crawlerLogs.slice(-200);
        renderLogs();
      }
    } catch (e) {
      // Ignore parse errors
    }
  };
  ws.onclose = function () {
    setTimeout(connectLogSocket, 5000);
  };
  ws.onerror = function () {
    // will trigger onclose
  };
}

// ── Fetch latest report on page load ──
async function fetchLatestReport() {
  try {
    var data = await api("/api/data/analysis-reports/latest");
    if (data && data.total > 0) {
      state.analysisReport = {
        total: data.total || 0,
        categories: data.categories || 0,
        aggregation: data.aggregation || [],
        classified_records: data.classified_preview || [],
        classified_count: data.classified_count || 0,
        solutions: data.solutions || 0,
        solutions_data: data.solutions_data || [],
        webhook_sent: data.webhook_sent || false,
        generated_at: data.generated_at || "",
      };
      renderAnalysisReport();
      appendLocalLog("info", "已加载最近分析报告：" + data.total + " 条数据，" + data.categories + " 个分类");
    }
  } catch (e) {
    // No reports yet — that's fine
  }
}

async function boot() {
  bindEvents();
  updateCrawlerPreview();
  renderAnalysisReport();
  await Promise.all([loadEnv(), loadConfig(), loadTasks(), loadLogs(), loadCrawlerStatus(), loadDataFiles(), loadWebhookStatus(), loadLlmConfig(), loadPipelineStatus(), fetchLatestReport()]);
  setInterval(loadLogs, 2500);
  setInterval(loadDataFiles, 8000);  // auto-refresh data files
  connectLogSocket();
  appendLocalLog("info", "控制台已启动，本机模式。");
}

boot();
