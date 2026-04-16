<script setup lang="ts">
import { onBeforeUnmount, onMounted } from "vue";
import { storeToRefs } from "pinia";
import FileUploadPanel from "./components/FileUploadPanel.vue";
import PreviewPanel from "./components/PreviewPanel.vue";
import ProviderPanel from "./components/ProviderPanel.vue";
import ResultPanel from "./components/ResultPanel.vue";
import { useRelationGraphStore } from "./stores/relationGraph";

const relationGraphStore = useRelationGraphStore();
const {
  apiKey,
  canLaunchLocalRuntimeTerminal,
  canStartLocalRuntime,
  currentResult,
  isLoading,
  model,
  previewUrl,
  providerStatus,
  rememberApiKey,
  selectedFiles,
  selectedLocalModel,
  selectedProvider,
  statusMessage,
  statusType
} = storeToRefs(relationGraphStore);

onMounted(async () => {
  await relationGraphStore.initialize();
});

onBeforeUnmount(() => {
  relationGraphStore.cleanup();
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
        :can-launch-local-runtime-terminal="canLaunchLocalRuntimeTerminal"
        @update:selected-provider="selectedProvider = $event; relationGraphStore.persistConfig()"
        @update:selected-local-model="selectedLocalModel = $event"
        @update:api-key="apiKey = $event; relationGraphStore.persistConfig()"
        @update:remember-api-key="rememberApiKey = $event; relationGraphStore.persistConfig()"
        @update:model="model = $event; relationGraphStore.persistConfig()"
        @start-local-runtime="relationGraphStore.startLocalRuntime"
        @launch-local-runtime-terminal="relationGraphStore.launchLocalRuntimeTerminal"
        @download-and-configure-models="relationGraphStore.downloadAndConfigureModels"
        @select-existing-model-dir="relationGraphStore.selectExistingModelDir"
        @change-preferred-local-model="relationGraphStore.changePreferredLocalModel"
      />

      <FileUploadPanel
        :selected-files="selectedFiles"
        @pick-files="relationGraphStore.pickFiles"
        @remove-file="relationGraphStore.removeFile"
        @drop-files="relationGraphStore.handleDrop"
      />

      <button class="primary-btn" type="button" :disabled="isLoading" @click="relationGraphStore.generateGraph">
        <span>{{ isLoading ? "任务处理中..." : "生成知识图谱" }}</span>
      </button>

      <div class="status" :class="statusType">{{ statusMessage }}</div>

      <ResultPanel
        v-if="currentResult"
        :result="currentResult"
        :fallback-model="model"
        @open-artifact="relationGraphStore.openArtifact"
        @export-standalone-graph="relationGraphStore.exportStandaloneGraph"
      />
    </aside>

    <PreviewPanel
      :preview-url="previewUrl"
      :graph-file-path="currentResult?.graphFilePath || null"
      :standalone-graph-file-path="currentResult?.standaloneGraphFilePath || null"
      @open-artifact="relationGraphStore.openArtifact"
      @export-standalone-graph="relationGraphStore.exportStandaloneGraph"
    />
  </div>
</template>
