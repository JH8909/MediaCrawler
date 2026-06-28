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
    $("taskRows").innerHTML = '<tr><td colspan="7" class="empty">暂无任务，点击“新建任务”写入一条。</td></tr>';
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

function normalizeReportRows(report) {
  if (!report) return [];
  const aggregation = Array.isArray(report.aggregation) ? report.aggregation : [];
  const solutions = Array.isArray(report.solutions_data) ? report.solutions_data : [];
  return aggregation.map((item) => {
    const category = item.category || item.name || "未分类";
    const count = Number(item.count || item.total || 0);
    return {
      category,
      count,
      solution: solutionTextForCategory(category, solutions),
    };
  });
}

function renderAnalysisReport(report) {
  if (report === undefined) report = state.analysisReport;
  var rowsEl = document.getElementById('analysisReportRows');
  if (!rowsEl) return;
  var hasReport = Boolean(report);
  var statusEl = document.getElementById('analysisReportStatus');
  if (statusEl) statusEl.textContent = hasReport ? '生成时间：' + (report.generated_at || '-') : '暂无报告';
  var el;
  el = document.getElementById('reportTotal'); if(el) el.textContent = hasReport ? String(report.total || 0) : '0';
  el = document.getElementById('reportCategories'); if(el) el.textContent = hasReport ? String(report.categories || 0) : '0';
  el = document.getElementById('reportSolutions'); if(el) el.textContent = hasReport ? String(report.solutions || 0) : '0';
  el = document.getElementById('reportWebhook'); if(el) el.textContent = hasReport && report.webhook_sent ? '已发送' : '未发送';

  var rows = normalizeReportRows(report);
  if (!rows.length) {
    rowsEl.innerHTML = '<tr><td colspan="4" class="empty">暂无分析报告。在“需求库”选择导出文件后生成报告。</td></tr>';
    return;
  }
  var html = '';
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i];
    html += '<tr class="clickable-row" data-category="' + escapeHtml(r.category) + '">';
    html += '<td style="color:var(--muted);font-size:12px">' + (i + 1) + '</td>';
    html += '<td><strong>' + escapeHtml(r.category) + '</strong></td>';
    html += '<td>' + r.count + '</td>';
    html += '<td>' + escapeHtml(r.solution || '-') + '</td>';
    html += '</tr>';
  }
  rowsEl.innerHTML = html;

  rowsEl.querySelectorAll('.clickable-row').forEach(function(tr) {
    tr.addEventListener('click', function() {
      var cat = tr.dataset.category;
      var sols = (state.analysisReport && state.analysisReport.solutions_data) || [];
      var filtered = filterSolutions(sols);
      openSolutionDialog(cat, filtered);
    });
  });
}async function analyzeAndReport(filePath) {
  if (!window.confirm(`将分析此文件并发送报告到飞书群：${filePath}\n确认继续？`)) {
    return;
  }
  try {
    appendLocalLog("info", "正在分析数据...");
    const data = await api("/api/data/analyze-report", {
      method: "POST",
      body: JSON.stringify({ file_path: filePath, dry_run: false, batch_size: 100 }),
    });
    state.analysisReport = {
      ...data,
      file_path: filePath,
      generated_at: new Date().toLocaleString("zh-CN", { hour12: false }),
    };
    renderAnalysisReport();
    $("dataPreviewBox").textContent = JSON.stringify(data, null, 2);
    if (data.webhook_sent) {
      appendLocalLog("success", `分析完成：${data.total} 条数据，${data.categories} 个分类，已发送飞书群报告`);
    } else {
      appendLocalLog("warning", `分析完成：${data.total} 条数据，${data.categories} 个分类，但 Webhook 未配置`);
    }
    if (data.solutions > 0) {
      appendLocalLog("info", `AI 已为 ${data.solutions} 个痛点生成解决方案`);
    }
  } catch (error) {
    appendLocalLog("error", `分析失败：${error.message}`);
  }
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

async function boot() {
  bindEvents();
  updateCrawlerPreview();
  renderAnalysisReport();
  await Promise.all([loadEnv(), loadConfig(), loadTasks(), loadLogs(), loadCrawlerStatus(), loadDataFiles(), loadWebhookStatus(), loadLlmConfig(), loadPipelineStatus()]);
  setInterval(loadLogs, 2500);
  setInterval(loadDataFiles, 8000);  // auto-refresh data files
  appendLocalLog("info", "控制台已启动，本机模式。");
}

boot();
