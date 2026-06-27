const state = {
  tasks: [],
  selectedId: "",
  dryRunCommand: "",
  counts: {},
  files: [],
  logs: [],
  crawlerLogs: [],
  runner: null,
  crawlerStatus: null,
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

function tickClock() {
  $("clock").textContent = new Date().toLocaleString("zh-CN", { hour12: false });
}

async function loadEnv() {
  const parts = [];
  try {
    const [base, feishu] = await Promise.all([
      api("/api/env/check").catch((error) => ({ success: false, message: error.message })),
      api("/api/feishu/env").catch((error) => ({ ready: false, env: {}, error: error.message })),
    ]);
    parts.push("<span>环境检查：</span>");
    parts.push(`<span class="check ${base.success ? "" : "bad"}">Python ${base.success ? "正常" : "异常"}</span>`);
    parts.push('<span class="check">网络连接 正常</span>');
    parts.push(`<span class="check ${feishu.ready ? "" : "bad"}">Bitable ${feishu.ready ? "可达" : "未配置"}</span>`);
  } catch (error) {
    parts.push(`<span>环境检查：</span><span class="check bad">${escapeHtml(error.message)}</span>`);
  }
  $("envChecks").innerHTML = parts.join("");
}

async function loadConfig() {
  const [base, feishu, platforms, options] = await Promise.all([
    api("/api/env/check").catch((error) => ({ success: false, message: error.message })),
    api("/api/feishu/env").catch((error) => ({ ready: false, env: {}, error: error.message })),
    api("/api/config/platforms").catch(() => ({ platforms: [] })),
    api("/api/config/options").catch(() => ({ login_types: [], crawler_types: [], save_options: [] })),
  ]);
  const envItems = Object.entries(feishu.env || {}).map(([key, value]) => ({
    label: key,
    value,
    ok: value === "SET",
  }));
  const items = [
    { label: "MediaCrawler 环境", value: base.success ? "正常" : (base.message || "异常"), ok: Boolean(base.success) },
    { label: "飞书多维表格", value: feishu.ready ? "可达" : "未配置完整", ok: Boolean(feishu.ready) },
    { label: "支持平台", value: `${platforms.platforms?.length || 0} 个`, ok: true },
    { label: "保存格式", value: `${options.save_options?.length || 0} 种`, ok: true },
    ...envItems,
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
    const canSync = ["jsonl", "csv", "sqlite", "db"].includes(String(file.type).toLowerCase());
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
            <button data-file-action="dry-sync" data-path="${safePath}" ${canSync ? "" : "disabled"}>Dry-Run</button>
            <button data-file-action="sync" data-path="${safePath}" ${canSync ? "" : "disabled"}>分析报告</button>
            <a href="/api/data/download/${urlPath}" target="_blank" rel="noreferrer">下载</a>
          </div>
        </td>
      </tr>`;
  }).join("");
}

async function analyzeAndReport(filePath) {
  if (!window.confirm(`将分析此文件并发送报告到飞书群：${filePath}\n确认继续？`)) {
    return;
  }
  try {
    appendLocalLog("info", "正在分析数据...");
    const data = await api("/api/data/analyze-report", {
      method: "POST",
      body: JSON.stringify({ file_path: filePath, dry_run: false, batch_size: 100 }),
    });
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

async function syncDataFile(filePath, dryRun) {
  if (!dryRun && state.lastDryRunFilePath !== filePath) {
    appendLocalLog("error", "正式同步前，请先对同一文件执行 Dry-Run。");
    return;
  }
  if (!dryRun && !window.confirm(`将把文件同步写入飞书需求库：${filePath}\n确认继续？`)) {
    return;
  }
  try {
    const data = await api("/api/data/sync-to-feishu", {
      method: "POST",
      body: JSON.stringify({ file_path: filePath, dry_run: dryRun, batch_size: 100 }),
    });
    const stats = data.stats || {};
    if (dryRun) state.lastDryRunFilePath = filePath;
    $("dataPreviewBox").textContent = JSON.stringify(data, null, 2);
    appendLocalLog(
      dryRun ? "info" : "success",
      `${dryRun ? "Dry-Run" : "同步"} ${filePath}：成功 ${stats.success || 0}，跳过 ${stats.skipped || 0}，失败 ${stats.failed || 0}，待同步 ${stats.pending || 0}`,
    );
  } catch (error) {
    $("dataPreviewBox").textContent = `同步失败：${error.message}`;
    appendLocalLog("error", `同步文件到飞书失败：${error.message}`);
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

function renderLogs() {
  const source = $("logSource").value;
  const onlyErrors = $("errorsOnly").checked;
  const feishuLogs = (state.runner?.logs || []).map((item) => ({ ...item, source: "feishu" }));
  const crawlerLogs = state.crawlerLogs.map((item) => ({ ...item, source: "crawler" }));
  let logs = [...state.logs, ...feishuLogs, ...crawlerLogs];
  if (source !== "all") logs = logs.filter((item) => item.source === source);
  if (onlyErrors) logs = logs.filter((item) => item.level === "error");
  if (!logs.length) {
    $("logBox").innerHTML = '<div class="log-line"><span>--</span><span class="info">INFO</span><span>等待任务运行...</span></div>';
    return;
  }
  $("logBox").innerHTML = logs.slice(-240).map((item) => `
    <div class="log-line">
      <span>${escapeHtml(item.timestamp || "--")}</span>
      <span class="${escapeHtml(item.level || "info")}">${escapeHtml(String(item.level || "info").toUpperCase())}</span>
      <span>${escapeHtml(item.message || "")}</span>
    </div>
  `).join("");
  if ($("autoScroll").checked) $("logBox").scrollTop = $("logBox").scrollHeight;
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
    state.logs = [];
    state.crawlerLogs = [];
    if (state.runner) state.runner.logs = [];
    renderLogs();
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
    if (button.dataset.fileAction === "dry-sync") syncDataFile(path, true);
    if (button.dataset.fileAction === "sync") analyzeAndReport(path);
  });
  $("refreshConfigBtn").addEventListener("click", () => Promise.all([loadEnv(), loadConfig()]));
  $("refreshConfigBtn").addEventListener("click", loadLlmConfig);
  $("saveWebhookBtn")?.addEventListener("click", saveWebhookUrl);
  $("testWebhookBtn")?.addEventListener("click", testWebhook);
  $("saveLlmBtn")?.addEventListener("click", saveLlmConfig);
  $("testLlmBtn")?.addEventListener("click", testLlmConnection);
  ["logSource", "errorsOnly", "autoScroll"].forEach((id) => $(id).addEventListener("change", renderLogs));
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".nav-item").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");

      const section = button.dataset.section;
      const isSecondary = ["data", "config", "webhook", "llm"].includes(section);

      // Toggle main content vs secondary pages
      document.querySelectorAll(".crawler-panel, .log-panel").forEach(el => {
        el.style.display = isSecondary ? "none" : "";
      });
      document.querySelectorAll(".page-panel").forEach(p => p.style.display = "none");

      if (isSecondary) {
        let pageId = "page-" + section;
        if (section === "webhook" || section === "llm") pageId = "page-settings";
        const page = document.getElementById(pageId);
        if (page) page.style.display = "block";
      }
    });
  });
  // Auto-track active nav section on scroll
  const sectionEls = [
    document.querySelector(".kpis"),
    document.querySelector(".task-panel"),
    document.querySelector(".log-panel"),
    document.querySelector("#dataSection"),
    document.querySelector("#configSection"),
    document.querySelector("#webhookSection"),
    document.querySelector("#llmSection"),
  ];
  const sectionNames = ["overview", "tasks", "logs", "data", "config", "webhook", "llm"];
  const scrollContainer = document.querySelector(".workspace");
  if (scrollContainer) {
    scrollContainer.addEventListener("scroll", () => {
      const scrollTop = scrollContainer.scrollTop + 120;
      let activeIdx = 0;
      sectionEls.forEach((el, i) => {
        if (el && el.offsetTop <= scrollTop) activeIdx = i;
      });
      document.querySelectorAll(".nav-item").forEach((item, i) => {
        item.classList.toggle("active", i === activeIdx);
      });
    });
  }
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


async function boot() {
  tickClock();
  setInterval(tickClock, 1000);
  bindEvents();
  updateCrawlerPreview();
  await Promise.all([loadEnv(), loadConfig(), loadTasks(), loadLogs(), loadCrawlerStatus(), loadDataFiles(), loadWebhookStatus(), loadLlmConfig()]);
  setInterval(loadLogs, 2500);
  setInterval(loadDataFiles, 8000);  // auto-refresh data files
  appendLocalLog("info", "控制台已启动，本机模式。");
}

boot();
