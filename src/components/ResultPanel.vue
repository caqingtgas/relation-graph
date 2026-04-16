<script setup lang="ts">
import { computed } from "vue";
import type { JobResult } from "../types";
import { buildMetaInfoText, buildWarningItems, buildWarningSummary } from "../utils/format";

const props = defineProps<{
  result: JobResult;
  fallbackModel: string;
}>();

const emit = defineEmits<{
  openArtifact: [string];
  exportStandaloneGraph: [];
}>();

const metadata = computed(() => props.result.metadata);
const providerLabel = computed(() => (props.result.providerMode === "local" ? "LOCAL" : "ARK"));
const summaryItems = computed(() => [
  { label: "实际提供商", value: providerLabel.value },
  { label: "使用模型", value: metadata.value.model || props.fallbackModel },
  { label: "节点数", value: `${metadata.value.node_count}` },
  { label: "最终关系", value: `${metadata.value.final_edge_count}` },
  { label: "文本块", value: `${metadata.value.chunk_count}` },
  { label: "失败块", value: `${metadata.value.failed_chunk_count}` },
  { label: "总 Tokens", value: `${metadata.value.token_usage.total_tokens}` },
  { label: "运行 ID", value: props.result.runId || "-" }
]);
const warningSummary = computed(() => buildWarningSummary(metadata.value));
const warningItems = computed(() => buildWarningItems(metadata.value));
const metaInfoText = computed(() => buildMetaInfoText(props.result.runId, metadata.value, props.fallbackModel));
</script>

<template>
  <div class="result-panel">
    <h3>生成成功</h3>
    <div class="result-summary">
      <div v-for="item in summaryItems" :key="item.label" class="result-summary-card">
        <span class="result-summary-card__label">{{ item.label }}</span>
        <span class="result-summary-card__value">{{ item.value }}</span>
      </div>
    </div>

    <div class="download-grid">
      <button class="result-link" type="button" @click="emit('openArtifact', result.chunksCsvFilePath)">📦 文本分块数据</button>
      <button class="result-link" type="button" @click="emit('openArtifact', result.graphCsvFilePath)">🔗 基础关系边</button>
      <button class="result-link" type="button" @click="emit('openArtifact', result.groupedGraphCsvFilePath)">🕸️ 聚合关系边</button>
      <button class="result-link" type="button" @click="emit('openArtifact', result.metadataFilePath)">📝 运行元数据</button>
      <button class="result-link" type="button" @click="emit('openArtifact', result.runDir)">📁 打开结果目录</button>
      <button class="result-link" type="button" @click="emit('exportStandaloneGraph')">⤓ 导出独立图谱</button>
    </div>

    <details class="result-details">
      <summary>查看详细元数据与失败块</summary>
      <div v-if="warningSummary" class="warning-summary">{{ warningSummary }}</div>
      <ul v-if="warningItems.length" class="warning-list">
        <li v-for="item in warningItems" :key="item">{{ item }}</li>
      </ul>
      <div class="meta-info">{{ metaInfoText }}</div>
    </details>
  </div>
</template>
