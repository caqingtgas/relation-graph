class AppController {
  constructor() {
    this.maxFiles = 10;
    this.maxTotalBytes = 25 * 1024 * 1024;
    this.providerPollIntervalMs = 5000;

    this.localModeBtn = document.getElementById("localModeBtn");
    this.cloudModeBtn = document.getElementById("cloudModeBtn");
    this.localPanel = document.getElementById("localPanel");
    this.cloudPanel = document.getElementById("cloudPanel");

    this.apiKeyInput = document.getElementById("apiKey");
    this.apiHint = document.getElementById("apiHint");
    this.rememberApiKeyInput = document.getElementById("rememberApiKey");
    this.modelInput = document.getElementById("model");
    this.filesInput = document.getElementById("files");
    this.dropZone = document.getElementById("dropZone");
    this.fileList = document.getElementById("fileList");
    this.fileSummary = document.getElementById("fileSummary");

    this.generateBtn = document.getElementById("generateBtn");
    this.btnText = document.getElementById("btnText");
    this.btnSpinner = document.getElementById("btnSpinner");
    this.startLocalRuntimeBtn = document.getElementById("startLocalRuntimeBtn");
    this.downloadModelBtn = document.getElementById("downloadModelBtn");
    this.useExistingModelDirBtn = document.getElementById("useExistingModelDirBtn");
    this.localModelSelect = document.getElementById("localModelSelect");

    this.providerModeBadge = document.getElementById("providerModeBadge");
    this.providerStatusText = document.getElementById("providerStatusText");
    this.localModelName = document.getElementById("localModelName");
    this.localModelDir = document.getElementById("localModelDir");

    this.statusBox = document.getElementById("statusBox");
    this.resultPanel = document.getElementById("resultPanel");
    this.resultSummary = document.getElementById("resultSummary");
    this.warningSummary = document.getElementById("warningSummary");
    this.warningList = document.getElementById("warningList");
    this.metaInfo = document.getElementById("metaInfo");

    this.graphFrame = document.getElementById("graphFrame");
    this.iframePlaceholder = document.getElementById("iframePlaceholder");
    this.saveGraphBtn = document.getElementById("saveGraphBtn");
    this.fullscreenBtn = document.getElementById("fullscreenBtn");

    this.currentGraphUrl = null;
    this.currentStandaloneGraphUrl = null;
    this.currentStandaloneGraphFilename = null;
    this.currentJobId = null;
    this.pollTimer = null;
    this.pollStatusUrl = null;
    this.providerPollTimer = null;
    this.keepProviderPolling = false;
    this.providerPollRemaining = 0;
    this.selectedFiles = [];
    this.providerStatus = null;
    this.selectedProvider = "local";

    this.init();
  }

  async init() {
    this.loadConfig();
    this.bindEvents();
    this.renderProviderPreference();
    await this.refreshProviderStatus({ silent: true });
  }

  loadConfig() {
    const remembered = localStorage.getItem("ark_remember_api_key") === "true";
    const localKey = localStorage.getItem("ark_api_key");
    const sessionKey = sessionStorage.getItem("ark_api_key");
    const savedModel = localStorage.getItem("ark_model_id");
    const savedProvider = localStorage.getItem("provider_mode_preference");

    this.rememberApiKeyInput.checked = remembered;
    if (remembered && localKey) {
      this.apiKeyInput.value = localKey;
    } else if (sessionKey) {
      this.apiKeyInput.value = sessionKey;
    }
    this.modelInput.value = savedModel || "doubao-seed-1-8-251228";
    this.selectedProvider = savedProvider === "ark" ? "ark" : "local";
  }

  saveConfig() {
    const apiKey = this.apiKeyInput.value.trim();
    const remember = this.rememberApiKeyInput.checked;
    localStorage.setItem("ark_model_id", this.modelInput.value.trim());
    localStorage.setItem("provider_mode_preference", this.selectedProvider);
    sessionStorage.setItem("ark_api_key", apiKey);

    if (remember && apiKey) {
      localStorage.setItem("ark_api_key", apiKey);
      localStorage.setItem("ark_remember_api_key", "true");
    } else {
      localStorage.removeItem("ark_api_key");
      localStorage.removeItem("ark_remember_api_key");
    }
  }

  setStatus(message, type = "info") {
    this.statusBox.classList.remove("hidden");
    this.statusBox.textContent = message;
    this.statusBox.className = `status ${type}`;
  }

  setLoading(isLoading) {
    this.generateBtn.disabled = isLoading;
    this.startLocalRuntimeBtn.disabled = isLoading;
    this.downloadModelBtn.disabled = isLoading;
    this.useExistingModelDirBtn.disabled = isLoading;
    this.localModelSelect.disabled = isLoading || this.localModelSelect.options.length === 0;
    this.localModeBtn.disabled = isLoading;
    this.cloudModeBtn.disabled = isLoading;
    if (isLoading) {
      this.btnText.textContent = "任务处理中...";
      this.btnSpinner.classList.remove("hidden");
    } else {
      this.btnText.textContent = "生成知识图谱";
      this.btnSpinner.classList.add("hidden");
    }
  }

  resetResultPreview() {
    this.resultPanel.classList.add("hidden");
    this.saveGraphBtn.classList.add("hidden");
    this.fullscreenBtn.classList.add("hidden");
    this.currentGraphUrl = null;
    this.currentStandaloneGraphUrl = null;
    this.currentStandaloneGraphFilename = null;
    this.graphFrame.src = "";
    this.graphFrame.classList.add("hidden");
    this.iframePlaceholder.classList.remove("hidden");
    this.resultSummary.innerHTML = "";
    this.warningSummary.textContent = "";
    this.warningSummary.classList.add("hidden");
    this.warningList.innerHTML = "";
    this.warningList.classList.add("hidden");
    this.metaInfo.textContent = "";
  }

  stopPolling() {
    if (this.pollTimer) {
      window.clearTimeout(this.pollTimer);
      this.pollTimer = null;
    }
    this.pollStatusUrl = null;
  }

  stopProviderPolling() {
    if (this.providerPollTimer) {
      window.clearTimeout(this.providerPollTimer);
      this.providerPollTimer = null;
    }
    this.keepProviderPolling = false;
    this.providerPollRemaining = 0;
  }

  startProviderPolling(maxAttempts = 24) {
    this.keepProviderPolling = true;
    this.providerPollRemaining = maxAttempts;
    this.scheduleProviderPoll(0);
  }

  scheduleProviderPoll(delayMs) {
    if (!this.keepProviderPolling || document.hidden || this.providerPollRemaining <= 0) {
      if (this.providerPollRemaining <= 0) {
        this.stopProviderPolling();
      }
      return;
    }
    if (this.providerPollTimer) {
      window.clearTimeout(this.providerPollTimer);
    }
    this.providerPollTimer = window.setTimeout(async () => {
      this.providerPollRemaining -= 1;
      const payload = await this.refreshProviderStatus({ silent: true });
      if (!payload) {
        this.scheduleProviderPoll(this.providerPollIntervalMs);
        return;
      }
      if (payload.local_runtime_status === "ready" || payload.local_runtime_status === "failed") {
        this.stopProviderPolling();
        return;
      }
      this.scheduleProviderPoll(this.providerPollIntervalMs);
    }, delayMs);
  }

  bindEvents() {
    this.localModeBtn.addEventListener("click", () => this.setProviderPreference("local"));
    this.cloudModeBtn.addEventListener("click", () => this.setProviderPreference("ark"));

    this.dropZone.addEventListener("click", () => this.filesInput.click());
    this.filesInput.addEventListener("change", (event) => this.handleFiles(event.target.files));
    this.fileList.addEventListener("click", (event) => this.handleFileListClick(event));
    document.addEventListener("visibilitychange", () => this.handleVisibilityChange());

    ["dragenter", "dragover", "dragleave", "drop"].forEach((eventName) => {
      this.dropZone.addEventListener(eventName, this.preventDefaults, false);
    });

    ["dragenter", "dragover"].forEach((eventName) => {
      this.dropZone.addEventListener(eventName, () => this.dropZone.classList.add("dragover"), false);
    });

    ["dragleave", "drop"].forEach((eventName) => {
      this.dropZone.addEventListener(eventName, () => this.dropZone.classList.remove("dragover"), false);
    });

    this.dropZone.addEventListener(
      "drop",
      (event) => {
        const dt = event.dataTransfer;
        this.handleFiles(dt.files);
      },
      false
    );

    this.generateBtn.addEventListener("click", () => this.generateGraph());
    this.startLocalRuntimeBtn.addEventListener("click", () => this.ensureLocalRuntimeStarted());
    this.downloadModelBtn.addEventListener("click", () => this.downloadAndConfigureModels());
    this.useExistingModelDirBtn.addEventListener("click", () => this.useExistingModelDir());
    this.localModelSelect.addEventListener("change", () => this.changePreferredLocalModel());
    this.saveGraphBtn.addEventListener("click", () => this.downloadStandaloneGraph());
    this.fullscreenBtn.addEventListener("click", () => {
      if (this.currentGraphUrl) {
        window.open(this.currentGraphUrl, "_blank");
      }
    });
  }

  handleVisibilityChange() {
    if (!document.hidden && this.keepProviderPolling) {
      this.scheduleProviderPoll(0);
    }
  }

  async setProviderPreference(mode) {
    this.selectedProvider = mode === "ark" ? "ark" : "local";
    localStorage.setItem("provider_mode_preference", this.selectedProvider);
    this.renderProviderPreference();
    if (this.selectedProvider === "ark") {
      this.stopProviderPolling();
      return;
    }
    await this.refreshProviderStatus({ silent: true });
  }

  renderProviderPreference() {
    const localActive = this.selectedProvider === "local";
    this.localModeBtn.classList.toggle("provider-switch__btn--active", localActive);
    this.cloudModeBtn.classList.toggle("provider-switch__btn--active", !localActive);
    this.localPanel.classList.toggle("hidden", !localActive);
    this.cloudPanel.classList.toggle("hidden", localActive);
  }

  preventDefaults(event) {
    event.preventDefault();
    event.stopPropagation();
  }

  async refreshProviderStatus({ silent = false } = {}) {
    try {
      const response = await fetch("/provider-status");
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "本地运行时状态查询失败。");
      }
      this.providerStatus = payload;
      this.renderProviderStatus(payload);
      return payload;
    } catch (error) {
      if (!silent) {
        this.setStatus(error.message, "error");
      }
      return null;
    }
  }

  renderProviderStatus(payload) {
    const providerMode = payload.provider_mode === "local" ? "local" : "ark";
    const runtimeStatus = payload.local_runtime_status || "not_configured";
    const detail = payload.detail || "本地运行时状态未知。";
    const modelName = payload.local_model_name || "未检测到";
    const modelDir = payload.local_model_dir || "尚未配置";
    const availableModels = Array.isArray(payload.available_local_models) ? payload.available_local_models : [];
    const preferredModel = payload.preferred_local_model || "qwen3.5:9b";
    const candidates = Array.isArray(payload.local_model_candidates) && payload.local_model_candidates.length > 0
      ? payload.local_model_candidates
      : ["qwen3.5:9b", "qwen3.5:4b"];

    this.providerModeBadge.textContent = providerMode === "local" ? "LOCAL" : runtimeStatus.toUpperCase();
    this.providerModeBadge.className = `provider-badge ${providerMode === "local" ? "provider-badge--local" : "provider-badge--ark"}`;
    this.providerStatusText.textContent = detail;
    this.localModelName.textContent = modelName;
    this.localModelDir.textContent = modelDir;

    this.populateLocalModelOptions(candidates, availableModels, preferredModel);

    const canStart = runtimeStatus === "stopped";
    this.startLocalRuntimeBtn.classList.toggle("hidden", !canStart);

    if (runtimeStatus === "ready") {
      this.apiHint.textContent = "云端模式下将直接使用火山方舟；本地模式已可用时，可随时切回本地。";
    } else {
      this.apiHint.textContent = "云端模式下将直接使用火山方舟。密钥只保存在当前浏览器，不会写入服务器或结果文件。";
    }
  }

  populateLocalModelOptions(candidates, availableModels, preferredModel) {
    const availableSet = new Set(availableModels);
    const nextOptions = candidates.map((modelId) => ({
      value: modelId,
      text: availableSet.has(modelId) ? modelId : `${modelId}（未就绪）`,
    }));
    const currentOptions = Array.from(this.localModelSelect.options).map((option) => ({
      value: option.value,
      text: option.textContent,
    }));

    const optionsChanged = JSON.stringify(currentOptions) !== JSON.stringify(nextOptions);
    if (optionsChanged) {
      this.localModelSelect.innerHTML = "";
      nextOptions.forEach((item) => {
        const option = document.createElement("option");
        option.value = item.value;
        option.textContent = item.text;
        this.localModelSelect.appendChild(option);
      });
    }

    this.localModelSelect.value = candidates.includes(preferredModel) ? preferredModel : candidates[0];
    this.localModelSelect.disabled = this.generateBtn.disabled || candidates.length === 0;
  }

  async ensureLocalRuntimeStarted() {
    this.startLocalRuntimeBtn.disabled = true;
    this.providerStatusText.textContent = "正在启动本地引擎...";
    try {
      const response = await fetch("/local-provider/ensure-started", { method: "POST" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "启动本地引擎失败。");
      }
      this.providerStatus = payload;
      this.renderProviderStatus(payload);
      this.setProviderPreference("local");
      this.setStatus(payload.detail || "本地引擎已启动。", payload.local_runtime_status === "ready" ? "success" : "info");
    } catch (error) {
      this.setStatus(error.message, "error");
      await this.refreshProviderStatus({ silent: true });
    } finally {
      this.startLocalRuntimeBtn.disabled = false;
    }
  }

  async downloadAndConfigureModels() {
    this.downloadModelBtn.disabled = true;
    this.providerStatusText.textContent = "正在打开目录窗口并准备下载模型...";
    try {
      const response = await fetch("/local-provider/download-and-configure", { method: "POST" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "下载模型并配置目录失败。");
      }
      this.providerStatus = payload;
      this.renderProviderStatus(payload);
      await this.setProviderPreference("local");
      this.setStatus(payload.detail || "已打开下载终端。", "info");
      this.startProviderPolling();
    } catch (error) {
      this.setStatus(error.message, "error");
      await this.refreshProviderStatus({ silent: true });
    } finally {
      this.downloadModelBtn.disabled = false;
    }
  }

  async useExistingModelDir() {
    this.useExistingModelDirBtn.disabled = true;
    this.providerStatusText.textContent = "正在打开目录选择窗口...";
    try {
      const response = await fetch("/local-provider/select-existing-dir", { method: "POST" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "绑定已有模型目录失败。");
      }
      this.providerStatus = payload;
      this.renderProviderStatus(payload);
      await this.setProviderPreference("local");
      this.setStatus(payload.detail || "本地模型目录已绑定。", payload.local_runtime_status === "ready" ? "success" : "info");
      if (payload.local_runtime_status === "missing_model") {
        this.startProviderPolling();
      }
    } catch (error) {
      this.setStatus(error.message, "error");
      await this.refreshProviderStatus({ silent: true });
    } finally {
      this.useExistingModelDirBtn.disabled = false;
    }
  }

  async changePreferredLocalModel() {
    const modelName = this.localModelSelect.value;
    if (!modelName) {
      return;
    }
    try {
      const formData = new FormData();
      formData.append("model_name", modelName);
      const response = await fetch("/local-provider/preferred-model", {
        method: "POST",
        body: formData,
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "切换本地模型失败。");
      }
      this.providerStatus = payload;
      this.renderProviderStatus(payload);
      this.setStatus(`本地优先模型已切换为 ${modelName}`, "success");
    } catch (error) {
      this.setStatus(error.message, "error");
      await this.refreshProviderStatus({ silent: true });
    }
  }

  handleFiles(fileList) {
    const candidateFiles = Array.from(fileList);
    const dedupedMap = new Map(this.selectedFiles.map((file) => [this.fileSignature(file), file]));

    candidateFiles.forEach((file) => {
      const ext = file.name.split(".").pop().toLowerCase();
      if (!["pdf", "txt", "md"].includes(ext)) {
        return;
      }
      dedupedMap.set(this.fileSignature(file), file);
    });

    this.selectedFiles = Array.from(dedupedMap.values());
    const validationError = this.validateSelectedFiles();
    this.renderFileList();

    if (validationError) {
      this.setStatus(validationError, "error");
      this.filesInput.value = "";
      return;
    }

    this.setStatus(`已就绪，准备处理 ${this.selectedFiles.length} 个文件`, "success");
    this.filesInput.value = "";
  }

  handleFileListClick(event) {
    const removeButton = event.target.closest("[data-remove-index]");
    if (!removeButton) {
      return;
    }
    const index = Number(removeButton.dataset.removeIndex);
    this.removeFile(index);
  }

  removeFile(index) {
    this.selectedFiles.splice(index, 1);
    this.renderFileList();
    if (this.selectedFiles.length === 0) {
      this.setStatus("请先上传知识源文件", "info");
      return;
    }
    const validationError = this.validateSelectedFiles();
    if (validationError) {
      this.setStatus(validationError, "error");
    } else {
      this.setStatus(`已就绪，准备处理 ${this.selectedFiles.length} 个文件`, "success");
    }
  }

  validateSelectedFiles() {
    if (this.selectedFiles.length === 0) {
      return "请上传支持的格式 (.pdf, .txt, .md)";
    }
    if (this.selectedFiles.length > this.maxFiles) {
      return `单次最多上传 ${this.maxFiles} 个文件，请减少后重试。`;
    }
    const totalBytes = this.selectedFiles.reduce((sum, file) => sum + file.size, 0);
    if (totalBytes > this.maxTotalBytes) {
      return `上传文件总大小超过上限 ${(this.maxTotalBytes / 1024 / 1024).toFixed(0)} MB，请减少文件后重试。`;
    }
    return "";
  }

  renderFileList() {
    if (this.selectedFiles.length === 0) {
      this.fileList.classList.add("hidden");
      this.fileSummary.classList.add("hidden");
      this.fileList.innerHTML = "";
      this.fileSummary.textContent = "";
      return;
    }

    const totalBytes = this.selectedFiles.reduce((sum, file) => sum + file.size, 0);
    this.fileSummary.classList.remove("hidden");
    this.fileSummary.textContent = `已选择 ${this.selectedFiles.length} 个文件，总大小 ${(totalBytes / 1024 / 1024).toFixed(2)} MB`;

    this.fileList.innerHTML = "";
    this.selectedFiles.forEach((file, index) => {
      const li = document.createElement("li");
      const size = `${(file.size / 1024 / 1024).toFixed(2)} MB`;
      li.innerHTML = `
        <div class="file-row">
          <span class="file-name">${file.name}</span>
          <span class="file-size">${size}</span>
        </div>
        <button type="button" class="file-remove-btn" data-remove-index="${index}" title="移除文件">移除</button>
      `;
      this.fileList.appendChild(li);
    });
    this.fileList.classList.remove("hidden");
  }

  fileSignature(file) {
    return `${file.name}__${file.size}__${file.lastModified}`;
  }

  async generateGraph() {
    const apiKey = this.apiKeyInput.value.trim();
    const model = this.modelInput.value.trim();
    const validationError = this.validateSelectedFiles();

    if (validationError) {
      this.setStatus(validationError, "error");
      return;
    }

    const providerStatus = await this.refreshProviderStatus({ silent: true });
    const localReady = providerStatus && providerStatus.local_runtime_status === "ready";

    if (this.selectedProvider === "local" && !localReady && providerStatus?.local_runtime_status !== "stopped") {
      this.setStatus("当前已切换到本地模式，但本地模型尚未就绪，请先下载模型、绑定已有模型目录，或手动启动本地引擎。", "error");
      return;
    }
    if (this.selectedProvider === "ark" && !apiKey) {
      this.setStatus("当前已切换到云端模式，请先填写火山方舟 API Key。", "error");
      return;
    }

    this.stopPolling();
    this.saveConfig();
    this.setLoading(true);
    this.resetResultPreview();
    this.setStatus(
      this.selectedProvider === "local"
        ? "当前使用本地模式，正在提交任务..."
        : "当前使用云端模式，正在提交任务...",
      "info"
    );

    const formData = new FormData();
    formData.append("api_key", apiKey);
    formData.append("model", model);
    formData.append("provider_preference", this.selectedProvider);
    this.selectedFiles.forEach((file) => formData.append("files", file));

    try {
      const response = await fetch("/generate", { method: "POST", body: formData });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "服务端返回异常，生成失败。");
      }

      this.currentJobId = payload.job_id;
      this.setStatus(payload.detail || "任务已创建，正在等待处理...", "info");
      this.startPolling(payload.status_url || `/jobs/${payload.job_id}`);
    } catch (error) {
      this.setStatus(error.message, "error");
      this.setLoading(false);
    }
  }

  startPolling(statusUrl) {
    this.pollStatusUrl = statusUrl;
    this.schedulePoll(0);
  }

  schedulePoll(delayMs) {
    if (!this.pollStatusUrl) {
      return;
    }
    const statusUrl = this.pollStatusUrl;
    this.stopPolling();
    this.pollStatusUrl = statusUrl;
    this.pollTimer = window.setTimeout(() => this.pollOnce(), delayMs);
  }

  async pollOnce() {
    if (!this.pollStatusUrl) {
      return;
    }
    try {
      const response = await fetch(this.pollStatusUrl, { method: "GET" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.detail || "任务状态查询失败。");
      }
      this.handleJobStatus(payload);
    } catch (error) {
      this.stopPolling();
      this.setLoading(false);
      this.setStatus(error.message, "error");
    }
  }

  handleJobStatus(payload) {
    const status = payload.status;
    const detail = payload.detail || "";
    const queuePosition = Number(payload.queue_position || 0);
    if (status === "queued") {
      const suffix = queuePosition > 0 ? ` 当前排队第 ${queuePosition} 位。` : "";
      this.setStatus((detail || "任务排队中...") + suffix, "info");
      this.pollStatusUrl = payload.status_url || this.pollStatusUrl;
      this.schedulePoll(2000);
      return;
    }

    if (status === "running") {
      this.setStatus(detail || "任务处理中...", "info");
      this.schedulePoll(1500);
      return;
    }

    if (status === "failed") {
      this.stopPolling();
      this.setLoading(false);
      this.setStatus(detail || "图谱生成失败。", "error");
      return;
    }

    if (status === "succeeded") {
      this.stopPolling();
      this.setLoading(false);
      this.handleSuccess(payload.result || {});
    }
  }

  renderResultSummary(items) {
    this.resultSummary.innerHTML = items
      .map(
        (item) => `
          <div class="result-summary-card">
            <span class="result-summary-card__label">${item.label}</span>
            <span class="result-summary-card__value">${item.value}</span>
          </div>
        `
      )
      .join("");
  }

  renderWarningDetails(meta) {
    const warningDetails = Array.isArray(meta.warning_details) ? meta.warning_details : [];
    const warnings = Array.isArray(meta.warnings) ? meta.warnings : [];
    const failedChunkCount = Number(meta.failed_chunk_count || 0);

    if (warningDetails.length > 0) {
      this.warningSummary.classList.remove("hidden");
      this.warningSummary.textContent = `共有 ${failedChunkCount} 个文本块抽取失败，以下是具体位置。`;
      this.warningList.classList.remove("hidden");
      this.warningList.innerHTML = warningDetails
        .map((item) => {
          const location = [
            item.source || "未知来源",
            item.page != null ? `第 ${item.page} 页` : null,
            `块 ${item.chunk_index}`,
          ]
            .filter(Boolean)
            .join(" / ");
          return `<li>${location}（${item.chunk_id}）：${item.error}</li>`;
        })
        .join("");
      return;
    }

    if (warnings.length > 0) {
      this.warningSummary.classList.remove("hidden");
      this.warningSummary.textContent = `共有 ${warnings.length} 条抽取警告。`;
      this.warningList.classList.remove("hidden");
      this.warningList.innerHTML = warnings.map((item) => `<li>${item}</li>`).join("");
      return;
    }

    this.warningSummary.classList.add("hidden");
    this.warningList.classList.add("hidden");
  }

  renderMetaInfo(payload, meta, usage, provider) {
    this.metaInfo.textContent =
      `运行 ID: ${payload.run_id}\n` +
      `实际提供商: ${provider}\n` +
      `使用模型: ${meta.model || this.modelInput.value}\n` +
      `源文件数: ${meta.source_file_count ?? this.selectedFiles.length}\n` +
      `解析块数: ${meta.chunk_count} 个\n` +
      `成功块数: ${meta.successful_chunk_count ?? meta.chunk_count}\n` +
      `失败块数: ${meta.failed_chunk_count ?? 0}\n` +
      `提取节点: ${meta.node_count} 个\n` +
      `最终关系: ${meta.final_edge_count} 条\n` +
      `社区分组: ${meta.community_count ?? "-"} 个\n` +
      `Prompt Tokens: ${usage.prompt_tokens ?? 0}\n` +
      `Completion Tokens: ${usage.completion_tokens ?? 0}\n` +
      `Total Tokens: ${usage.total_tokens ?? 0}`;
  }

  handleSuccess(payload) {
    const meta = payload.metadata || {};
    const usage = meta.token_usage || {};
    const provider = meta.provider === "local" ? "LOCAL" : "ARK";
    const totalTokens = Number(usage.total_tokens || 0);
    const failedChunkCount = Number(meta.failed_chunk_count || 0);
    const successMessage = totalTokens > 0
      ? `图谱生成成功，本次使用 ${provider}，累计消耗 ${totalTokens} tokens。`
      : `图谱生成成功，本次使用 ${provider}。`;
    const finalMessage = failedChunkCount > 0
      ? `${successMessage} 已基于成功块生成，存在 ${failedChunkCount} 个文本块抽取失败。`
      : successMessage;
    this.setStatus(finalMessage, failedChunkCount > 0 ? "info" : "success");

    this.resultPanel.classList.remove("hidden");
    this.renderResultSummary([
      { label: "实际提供商", value: provider },
      { label: "使用模型", value: meta.model || this.modelInput.value },
      { label: "节点数", value: `${meta.node_count ?? 0}` },
      { label: "最终关系", value: `${meta.final_edge_count ?? 0}` },
      { label: "文本块", value: `${meta.chunk_count ?? 0}` },
      { label: "失败块", value: `${failedChunkCount}` },
      { label: "总 Tokens", value: `${totalTokens}` },
      { label: "运行 ID", value: payload.run_id || "-" },
    ]);
    document.getElementById("chunksLink").href = payload.chunks_csv_url;
    document.getElementById("graphLink").href = payload.graph_csv_url;
    document.getElementById("groupedGraphLink").href = payload.grouped_graph_csv_url;
    document.getElementById("metaLink").href = payload.metadata_url;
    this.renderWarningDetails(meta);
    this.renderMetaInfo(payload, meta, usage, provider);

    this.currentGraphUrl = payload.graph_url;
    this.currentStandaloneGraphUrl = payload.standalone_graph_url || payload.graph_url;
    this.currentStandaloneGraphFilename = `graph_${payload.run_id || "export"}.html`;
    this.iframePlaceholder.classList.add("hidden");
    this.graphFrame.classList.remove("hidden");
    this.graphFrame.src = this.currentGraphUrl;
    this.saveGraphBtn.classList.remove("hidden");
    this.fullscreenBtn.classList.remove("hidden");
  }

  downloadStandaloneGraph() {
    if (!this.currentStandaloneGraphUrl) {
      return;
    }
    const link = document.createElement("a");
    link.href = this.currentStandaloneGraphUrl;
    if (this.currentStandaloneGraphFilename) {
      link.download = this.currentStandaloneGraphFilename;
    }
    document.body.appendChild(link);
    link.click();
    link.remove();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  new AppController();
});
