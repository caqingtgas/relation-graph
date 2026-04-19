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
      <header class="workspace-head">
        <div class="workspace-head__copy">
          <h1>关系织图</h1>
          <p class="subtitle">把文本文档图谱化建模成关系图谱</p>
        </div>
      </header>

      <ProviderPanel
        :selected-provider="selectedProvider"
        :provider-status="providerStatus"
        :selected-local-model="selectedLocalModel"
        :api-key="apiKey"
        :remember-api-key="rememberApiKey"
        :model="model"
        :is-loading="isLoading"
        @update:selected-provider="selectedProvider = $event; relationGraphStore.persistConfig()"
        @update:selected-local-model="selectedLocalModel = $event"
        @update:api-key="apiKey = $event; relationGraphStore.persistConfig()"
        @update:remember-api-key="rememberApiKey = $event; relationGraphStore.persistConfig()"
        @update:model="model = $event; relationGraphStore.persistConfig()"
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
