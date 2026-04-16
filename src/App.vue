<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import FileUploadPanel from "./components/FileUploadPanel.vue";
import PreviewPanel from "./components/PreviewPanel.vue";
import ProviderPanel from "./components/ProviderPanel.vue";
import ResultPanel from "./components/ResultPanel.vue";
import { loadConfig, saveConfig } from "./services/configStore";
import { createJobPoller } from "./services/jobPolling";
import { getRelationGraphApi } from "./services/relationGraphApi";
import type { DesktopInputFile, JobPayload, JobResult, ProviderPreference, ProviderStatus } from "./types";
import { isSupportedFileName } from "./utils/format";

const defaultModel = "doubao-seed-1-8-251228";
const maxFiles = 10;
const maxTotalBytes = 25 * 1024 * 1024;

const selectedProvider = ref<ProviderPreference>("local");
const providerStatus = ref<ProviderStatus | null>(null);
const apiKey = ref("");
const rememberApiKey = ref(false);
const model = ref(defaultModel);
const selectedFiles = ref<DesktopInputFile[]>([]);
const selectedLocalModel = ref("qwen3.5:9b");
const statusMessage = ref("正在检测本地ollama...");
const statusType = ref<"info" | "success" | "error">("info");
const isLoading = ref(false);
const currentJob = ref<JobPayload | null>(null);
const currentResult = ref<JobResult | null>(null);
const previewUrl = ref("");
const relationGraphApi = getRelationGraphApi();

const canStartLocalRuntime = computed(() => providerStatus.value?.localRuntimeStatus === "stopped");

const poller = createJobPoller(relationGraphApi.getJobStatus, handleJobUpdate, (error) => {
  isLoading.value = false;
  setStatus(error.message, "error");
});

function setStatus(message: string, type: "info" | "success" | "error" = "info") {
  statusMessage.value = message;
  statusType.value = type;
}

function hasSpecificStatusDetail(status: ProviderStatus | null) {
  return Boolean(status?.detail?.trim() && status.detail.trim() !== "stopped");
}

function getProviderStatusType(status: ProviderStatus) {
  return status.localRuntimeStatus === "ready" ? "success" : "info";
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
  const saved = loadConfig(defaultModel);
  selectedProvider.value = saved.provider;
  apiKey.value = saved.apiKey;
  rememberApiKey.value = saved.rememberApiKey;
  model.value = saved.model;
}

function validateSelectedFiles() {
  if (selectedFiles.value.length === 0) {
    return "请上传支持的格式 (.pdf, .txt, .md)";
  }
  if (selectedFiles.value.length > maxFiles) {
    return `单次最多上传 ${maxFiles} 个文件，请减少后重试。`;
  }
  const totalBytes = selectedFiles.value.reduce((sum, file) => sum + file.size, 0);
  if (totalBytes > maxTotalBytes) {
    return `上传文件总大小超过上限 ${(maxTotalBytes / 1024 / 1024).toFixed(0)} MB，请减少文件后重试。`;
  }
  return "";
}

function mergeInputFiles(nextFiles: DesktopInputFile[]) {
  const map = new Map(selectedFiles.value.map((file) => [file.path, file]));
  nextFiles.forEach((file) => map.set(file.path, file));
  selectedFiles.value = Array.from(map.values());
}

async function refreshProviderStatus(silent = false) {
  try {
    providerStatus.value = await relationGraphApi.getProviderStatus();
    selectedLocalModel.value = providerStatus.value.preferredLocalModel || "qwen3.5:9b";
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
  mergeInputFiles(nextFiles);
  const validationError = validateSelectedFiles();
  if (validationError) {
    setStatus(validationError, "error");
    return;
  }
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
  mergeInputFiles(supportedDroppedFiles);
  const validationError = validateSelectedFiles();
  if (validationError) {
    setStatus(validationError, "error");
    return;
  }
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

async function startLocalRuntime() {
  try {
    providerStatus.value = await relationGraphApi.ensureLocalRuntimeStarted();
    selectedLocalModel.value = providerStatus.value.preferredLocalModel || selectedLocalModel.value;
    setStatus(providerStatus.value.detail, providerStatus.value.localRuntimeStatus === "ready" ? "success" : "info");
  } catch (error) {
    setStatus((error as Error).message, "error");
  }
}

async function selectExistingModelDir() {
  try {
    providerStatus.value = await relationGraphApi.selectExistingModelDir();
    selectedLocalModel.value = providerStatus.value.preferredLocalModel || selectedLocalModel.value;
    setStatus(providerStatus.value.detail, providerStatus.value.localRuntimeStatus === "ready" ? "success" : "info");
  } catch (error) {
    setStatus((error as Error).message, "error");
  }
}

async function downloadAndConfigureModels() {
  try {
    providerStatus.value = await relationGraphApi.downloadAndConfigureModels();
    selectedLocalModel.value = providerStatus.value.preferredLocalModel || selectedLocalModel.value;
    setStatus(providerStatus.value.detail, "info");
  } catch (error) {
    setStatus((error as Error).message, "error");
  }
}

async function changePreferredLocalModel() {
  try {
    providerStatus.value = await relationGraphApi.setPreferredLocalModel(selectedLocalModel.value);
    setStatus(`本地优先模型已切换为 ${selectedLocalModel.value}`, "success");
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
  previewUrl.value = await relationGraphApi.toFileUrl(result.standaloneGraphFilePath || result.graphFilePath);
  const totalTokens = Number(result.metadata.token_usage.total_tokens || 0);
  const failedChunkCount = Number(result.metadata.failed_chunk_count || 0);
  const provider = result.providerMode === "local" ? "LOCAL" : "ARK";
  const successMessage = totalTokens > 0
    ? `图谱生成成功，本次使用 ${provider}，累计消耗 ${totalTokens} tokens。`
    : `图谱生成成功，本次使用 ${provider}。`;
  setStatus(
    failedChunkCount > 0 ? `${successMessage} 已基于成功块生成，存在 ${failedChunkCount} 个文本块抽取失败。` : successMessage,
    failedChunkCount > 0 ? "info" : "success"
  );
}

function handleJobUpdate(payload: JobPayload) {
  currentJob.value = payload;
  if (payload.status === "queued") {
    const suffix = payload.queuePosition ? ` 当前排队第 ${payload.queuePosition} 位。` : "";
    setStatus((payload.detail || "任务排队中...") + suffix, "info");
    poller.schedule(payload.jobId, 2000);
    return;
  }
  if (payload.status === "running") {
    setStatus(payload.detail || "任务处理中...", "info");
    poller.schedule(payload.jobId, 1500);
    return;
  }
  if (payload.status === "failed") {
    poller.stop();
    isLoading.value = false;
    setStatus(payload.detail || "图谱生成失败。", "error");
    return;
  }
  if (payload.status === "succeeded" && payload.result) {
    poller.stop();
    isLoading.value = false;
    void handleSuccess(payload.result);
  }
}

async function generateGraph() {
  const validationError = validateSelectedFiles();
  if (validationError) {
    setStatus(validationError, "error");
    return;
  }

  const provider = await refreshProviderStatus(true);
  if (!provider) {
    setStatus("桌面后端未就绪，请重启应用后重试。", "error");
    return;
  }
  const localReady = provider.localRuntimeStatus === "ready";
  if (selectedProvider.value === "local" && !localReady && provider.localRuntimeStatus !== "stopped") {
    setStatus("当前已切换到本地模式，但本地模型尚未就绪，请先下载模型、绑定已有模型目录，或手动启动本地引擎。", "error");
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
    "info"
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
    setStatus((error as Error).message, "error");
  }
}

async function openArtifact(path: string) {
  await relationGraphApi.openRunArtifact(path);
}

async function exportStandaloneGraph() {
  if (!currentResult.value) {
    return;
  }
  await relationGraphApi.exportStandaloneGraph(currentResult.value.standaloneGraphFilePath);
}

onMounted(async () => {
  restoreConfig();
  const initialStatus = await refreshProviderStatus();
  if (statusType.value === "error") {
    return;
  }
  if (initialStatus && hasSpecificStatusDetail(initialStatus)) {
    setStatus(initialStatus.detail, getProviderStatusType(initialStatus));
    return;
  }
  if (statusMessage.value === "正在检测本地ollama...") {
    setStatus("请选择文件并开始生成图谱。");
  }
});

onBeforeUnmount(() => {
  poller.stop();
});
</script>

<template>
  <div class="page">
    <aside class="sidebar">
      <header>
        <h1>关系图谱引擎</h1>
        <p class="subtitle">将非结构化文档转化为可视化的知识网络</p>
      </header>

      <ProviderPanel
        :selected-provider="selectedProvider"
        :provider-status="providerStatus"
        :selected-local-model="selectedLocalModel"
        :api-key="apiKey"
        :remember-api-key="rememberApiKey"
        :model="model"
        :is-loading="isLoading"
        :can-start-local-runtime="canStartLocalRuntime"
        @update:selected-provider="selectedProvider = $event; persistConfig()"
        @update:selected-local-model="selectedLocalModel = $event"
        @update:api-key="apiKey = $event; persistConfig()"
        @update:remember-api-key="rememberApiKey = $event; persistConfig()"
        @update:model="model = $event; persistConfig()"
        @start-local-runtime="startLocalRuntime"
        @download-and-configure-models="downloadAndConfigureModels"
        @select-existing-model-dir="selectExistingModelDir"
        @change-preferred-local-model="changePreferredLocalModel"
      />

      <FileUploadPanel :selected-files="selectedFiles" @pick-files="pickFiles" @remove-file="removeFile" @drop-files="handleDrop" />

      <button class="primary-btn" type="button" :disabled="isLoading" @click="generateGraph">
        <span>{{ isLoading ? "任务处理中..." : "生成知识图谱" }}</span>
      </button>

      <div class="status" :class="statusType">{{ statusMessage }}</div>

      <ResultPanel
        v-if="currentResult"
        :result="currentResult"
        :fallback-model="model"
        @open-artifact="openArtifact"
        @export-standalone-graph="exportStandaloneGraph"
      />
    </aside>

    <PreviewPanel
      :preview-url="previewUrl"
      :graph-file-path="currentResult?.graphFilePath || null"
      :standalone-graph-file-path="currentResult?.standaloneGraphFilePath || null"
      @open-artifact="openArtifact"
      @export-standalone-graph="exportStandaloneGraph"
    />
  </div>
</template>
