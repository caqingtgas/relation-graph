import { ref, watch } from "vue";
import { defineStore } from "pinia";
import { loadConfig, saveConfig } from "../services/configStore";
import { createJobPoller } from "../services/jobPolling";
import { getRelationGraphApi } from "../services/relationGraphApi";
import type { DesktopInputFile, JobPayload, JobResult, ProviderPreference, ProviderStatus } from "../types";
import { isSupportedFileName } from "../utils/format";

const DEFAULT_MODEL = "doubao-seed-1-8-251228";
const DEFAULT_LOCAL_MODEL = "qwen3.5:9b";
const MAX_FILES = 10;
const MAX_TOTAL_BYTES = 25 * 1024 * 1024;

export const useRelationGraphStore = defineStore("relationGraph", () => {
  const relationGraphApi = getRelationGraphApi();

  const selectedProvider = ref<ProviderPreference>("local");
  const providerStatus = ref<ProviderStatus | null>(null);
  const apiKey = ref("");
  const rememberApiKey = ref(false);
  const model = ref(DEFAULT_MODEL);
  const selectedFiles = ref<DesktopInputFile[]>([]);
  const selectedLocalModel = ref(DEFAULT_LOCAL_MODEL);
  const statusMessage = ref("正在检测本地引擎...");
  const statusType = ref<"info" | "success" | "error">("info");
  const statusOwner = ref<"provider" | "user" | "job">("provider");
  const isLoading = ref(false);
  const currentJob = ref<JobPayload | null>(null);
  const currentResult = ref<JobResult | null>(null);
  const previewUrl = ref("");
  let providerRefreshTimer: number | null = null;

  function setStatus(
    message: string,
    type: "info" | "success" | "error" = "info",
    owner: "provider" | "user" | "job" = "user"
  ) {
    statusMessage.value = message;
    statusType.value = type;
    statusOwner.value = owner;
  }

  function setProviderStatusMessage(status: ProviderStatus, force = false) {
    if (!status.detail || (!force && statusOwner.value !== "provider")) {
      return;
    }
    setStatus(status.detail, getProviderStatusType(status), "provider");
  }

  function clearProviderRefreshTimer() {
    if (providerRefreshTimer !== null) {
      window.clearTimeout(providerRefreshTimer);
      providerRefreshTimer = null;
    }
  }

  function shouldAutoRefreshLocalProvider(status: ProviderStatus | null) {
    if (!status) {
      return false;
    }
    return selectedProvider.value === "local" && status.localRuntimeStatus !== "ready";
  }

  function scheduleProviderRefresh(attemptsRemaining = 12, delayMs = 2500) {
    clearProviderRefreshTimer();
    if (attemptsRemaining <= 0) {
      return;
    }
    providerRefreshTimer = window.setTimeout(async () => {
      const nextStatus = await refreshProviderStatus(true, true);
      if (nextStatus) {
        setProviderStatusMessage(nextStatus);
      }
      if (!shouldAutoRefreshLocalProvider(nextStatus)) {
        clearProviderRefreshTimer();
        return;
      }
      scheduleProviderRefresh(attemptsRemaining - 1, delayMs);
    }, delayMs);
  }

  function persistConfig() {
    saveConfig({
      provider: selectedProvider.value,
      apiKey: apiKey.value,
      rememberApiKey: rememberApiKey.value,
      model: model.value
    });
  }

  function restoreConfig() {
    const saved = loadConfig(DEFAULT_MODEL);
    selectedProvider.value = saved.provider;
    apiKey.value = saved.apiKey;
    rememberApiKey.value = saved.rememberApiKey;
    model.value = saved.model;
  }

  function hasSpecificStatusDetail(status: ProviderStatus | null) {
    return Boolean(status?.detail?.trim() && status.detail.trim() !== "stopped");
  }

  function getProviderStatusType(status: ProviderStatus) {
    return status.localRuntimeStatus === "ready" ? "success" : "info";
  }

  function validateInputFiles(files: DesktopInputFile[]) {
    if (files.length === 0) {
      return "请上传支持的格式 (.pdf, .txt, .md)";
    }
    if (files.length > MAX_FILES) {
      return `单次最多上传 ${MAX_FILES} 个文件，请减少后重试。`;
    }
    const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
    if (totalBytes > MAX_TOTAL_BYTES) {
      return `上传文件总大小超过上限 ${(MAX_TOTAL_BYTES / 1024 / 1024).toFixed(0)} MB，请减少文件后重试。`;
    }
    return "";
  }

  function validateSelectedFiles() {
    return validateInputFiles(selectedFiles.value);
  }

  function buildMergedInputFiles(nextFiles: DesktopInputFile[]) {
    const map = new Map(selectedFiles.value.map((file) => [file.path, file]));
    nextFiles.forEach((file) => map.set(file.path, file));
    return Array.from(map.values());
  }

  async function refreshProviderStatus(silent = false, autoStartLocal = false) {
    try {
      providerStatus.value = await relationGraphApi.getProviderStatus({
        autoStart: autoStartLocal && selectedProvider.value === "local"
      });
      selectedLocalModel.value = providerStatus.value.preferredLocalModel || DEFAULT_LOCAL_MODEL;
      return providerStatus.value;
    } catch (error) {
      if (!silent) {
        setStatus((error as Error).message, "error");
      }
      return null;
    }
  }

  async function pickFiles() {
    const nextFiles = await relationGraphApi.pickInputFiles();
    if (nextFiles.length === 0) {
      return;
    }
    const mergedFiles = buildMergedInputFiles(nextFiles);
    const validationError = validateInputFiles(mergedFiles);
    if (validationError) {
      setStatus(validationError, "error");
      return;
    }
    selectedFiles.value = mergedFiles;
    setStatus(`已就绪，准备处理 ${selectedFiles.value.length} 个文件`, "success");
  }

  function handleDrop(event: DragEvent) {
    const droppedFiles = Array.from(event.dataTransfer?.files || [])
      .map((file) => {
        const desktopFile = file as File & { path?: string };
        if (!desktopFile.path) {
          return null;
        }
        return {
          path: desktopFile.path,
          name: file.name,
          size: file.size
        };
      })
      .filter((file): file is DesktopInputFile => Boolean(file));

    const supportedDroppedFiles = droppedFiles.filter((file) => isSupportedFileName(file.name));
    if (supportedDroppedFiles.length === 0) {
      if (droppedFiles.length > 0) {
        setStatus("拖拽文件中仅支持 .pdf、.txt、.md 格式。", "error");
      }
      return;
    }

    const mergedFiles = buildMergedInputFiles(supportedDroppedFiles);
    const validationError = validateInputFiles(mergedFiles);
    if (validationError) {
      setStatus(validationError, "error");
      return;
    }
    selectedFiles.value = mergedFiles;
    if (supportedDroppedFiles.length !== droppedFiles.length) {
      setStatus(`已忽略不支持的文件，仅保留 ${supportedDroppedFiles.length} 个可处理文件。`, "info");
      return;
    }
    setStatus(`已就绪，准备处理 ${selectedFiles.value.length} 个文件`, "success");
  }

  function removeFile(filePath: string) {
    selectedFiles.value = selectedFiles.value.filter((file) => file.path !== filePath);
    if (selectedFiles.value.length === 0) {
      setStatus("请先上传知识源文件", "info");
      return;
    }
    const validationError = validateSelectedFiles();
    setStatus(validationError || `已就绪，准备处理 ${selectedFiles.value.length} 个文件`, validationError ? "error" : "success");
  }

  async function selectExistingModelDir() {
    try {
      providerStatus.value = await relationGraphApi.selectExistingModelDir();
      selectedLocalModel.value = providerStatus.value.preferredLocalModel || selectedLocalModel.value;
      setProviderStatusMessage(providerStatus.value, true);
      if (shouldAutoRefreshLocalProvider(providerStatus.value)) {
        scheduleProviderRefresh();
      }
    } catch (error) {
      setStatus((error as Error).message, "error");
    }
  }

  async function downloadAndConfigureModels() {
    try {
      providerStatus.value = await relationGraphApi.downloadAndConfigureModels();
      selectedLocalModel.value = providerStatus.value.preferredLocalModel || selectedLocalModel.value;
      setProviderStatusMessage(providerStatus.value, true);
      scheduleProviderRefresh();
    } catch (error) {
      setStatus((error as Error).message, "error");
    }
  }

  async function changePreferredLocalModel() {
    try {
      providerStatus.value = await relationGraphApi.setPreferredLocalModel(selectedLocalModel.value);
      setStatus(`本地优先模型已切换为 ${selectedLocalModel.value}`, "success", "provider");
    } catch (error) {
      setStatus((error as Error).message, "error");
    }
  }

  function resetResultPreview() {
    currentResult.value = null;
    previewUrl.value = "";
  }

  async function handleSuccess(result: JobResult) {
    currentResult.value = result;
    previewUrl.value = await relationGraphApi.toPreviewUrl(result.standaloneGraphFilePath || result.graphFilePath);
    const totalTokens = Number(result.metadata.token_usage.total_tokens || 0);
    const failedChunkCount = Number(result.metadata.failed_chunk_count || 0);
    const provider = result.providerMode === "local" ? "LOCAL" : "ARK";
    const successMessage = totalTokens > 0
      ? `图谱生成成功，本次使用 ${provider}，累计消耗 ${totalTokens} tokens。`
      : `图谱生成成功，本次使用 ${provider}。`;
    setStatus(
      failedChunkCount > 0 ? `${successMessage} 已基于成功块生成，存在 ${failedChunkCount} 个文本块抽取失败。` : successMessage,
      failedChunkCount > 0 ? "info" : "success",
      "job"
    );
  }

  function handleJobUpdate(payload: JobPayload) {
    currentJob.value = payload;
    if (payload.status === "queued") {
      const suffix = payload.queuePosition ? ` 当前排队第 ${payload.queuePosition} 位。` : "";
      setStatus((payload.detail || "任务排队中...") + suffix, "info", "job");
      poller.schedule(payload.jobId, 2000);
      return;
    }
    if (payload.status === "running") {
      setStatus(payload.detail || "任务处理中...", "info", "job");
      poller.schedule(payload.jobId, 1500);
      return;
    }
    if (payload.status === "failed") {
      poller.stop();
      isLoading.value = false;
      setStatus(payload.detail || "图谱生成失败。", "error", "job");
      return;
    }
    if (payload.status === "succeeded" && payload.result) {
      poller.stop();
      isLoading.value = false;
      void handleSuccess(payload.result);
    }
  }

  const poller = createJobPoller(relationGraphApi.getJobStatus, handleJobUpdate, (error) => {
    isLoading.value = false;
    setStatus(error.message, "error", "job");
  });

  async function generateGraph() {
    const validationError = validateSelectedFiles();
    if (validationError) {
      setStatus(validationError, "error");
      return;
    }

    const provider = await refreshProviderStatus(true);
    if (!provider) {
      setStatus("桌面引擎未就绪，请重启应用后重试。", "error");
      return;
    }
    const localReady = provider.localRuntimeStatus === "ready";
    if (selectedProvider.value === "local" && !localReady && provider.localRuntimeStatus !== "stopped") {
      setStatus("当前已切换到本地模式，但本地模型尚未就绪，请先下载模型或绑定已有模型目录；应用会自动持续检测本地引擎状态。", "error");
      return;
    }
    if (selectedProvider.value === "ark" && !apiKey.value.trim()) {
      setStatus("当前已切换到云端模式，请先填写火山方舟 API Key。", "error");
      return;
    }

    poller.stop();
    persistConfig();
    isLoading.value = true;
    resetResultPreview();
    setStatus(
      selectedProvider.value === "local" ? "当前使用本地模式，正在提交任务..." : "当前使用云端模式，正在提交任务...",
      "info",
      "job"
    );

    try {
      const payload = await relationGraphApi.submitJob({
        api_key: apiKey.value.trim(),
        model: model.value.trim(),
        provider_preference: selectedProvider.value,
        files: selectedFiles.value.map((file) => file.path)
      });
      handleJobUpdate(payload);
    } catch (error) {
      isLoading.value = false;
      setStatus((error as Error).message, "error", "job");
    }
  }

  async function openArtifact(targetPath: string) {
    try {
      await relationGraphApi.openRunArtifact(targetPath);
    } catch (error) {
      setStatus((error as Error).message, "error");
    }
  }

  async function exportStandaloneGraph() {
    if (!currentResult.value) {
      return;
    }
    try {
      await relationGraphApi.exportStandaloneGraph(currentResult.value.standaloneGraphFilePath);
      setStatus("独立图谱已导出。", "success");
    } catch (error) {
      setStatus((error as Error).message, "error");
    }
  }

  async function initialize() {
    restoreConfig();
    const initialStatus = await refreshProviderStatus(false, selectedProvider.value === "local");
    if (statusType.value === "error") {
      return;
    }
    if (shouldAutoRefreshLocalProvider(initialStatus)) {
      scheduleProviderRefresh();
    }
    if (initialStatus && hasSpecificStatusDetail(initialStatus)) {
      setProviderStatusMessage(initialStatus, true);
      return;
    }
    if (statusMessage.value === "正在检测本地引擎...") {
      setStatus("请选择文件并开始生成图谱。");
    }
  }

  function cleanup() {
    poller.stop();
    clearProviderRefreshTimer();
  }

  watch(selectedProvider, async (nextProvider) => {
    if (nextProvider !== "local") {
      clearProviderRefreshTimer();
      return;
    }
    const currentStatus = providerStatus.value ?? await refreshProviderStatus(true, true);
    if (!currentStatus) {
      return;
    }
    if (currentStatus.detail) {
      setProviderStatusMessage(currentStatus, true);
    }
    if (shouldAutoRefreshLocalProvider(currentStatus)) {
      scheduleProviderRefresh();
      return;
    }
    clearProviderRefreshTimer();
  });

  return {
    apiKey,
    currentResult,
    generateGraph,
    handleDrop,
    initialize,
    isLoading,
    model,
    openArtifact,
    pickFiles,
    previewUrl,
    providerStatus,
    rememberApiKey,
    removeFile,
    selectedFiles,
    selectedLocalModel,
    selectedProvider,
    setStatus,
    statusMessage,
    statusType,
    cleanup,
    changePreferredLocalModel,
    downloadAndConfigureModels,
    exportStandaloneGraph,
    persistConfig,
    selectExistingModelDir
  };
});
