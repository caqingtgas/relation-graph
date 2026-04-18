<script setup lang="ts">
import { computed } from "vue";
import type { DesktopInputFile } from "../types";
import { formatBytes } from "../utils/format";

const props = defineProps<{
  selectedFiles: DesktopInputFile[];
}>();

const emit = defineEmits<{
  pickFiles: [];
  removeFile: [string];
  dropFiles: [DragEvent];
}>();

const totalSize = computed(() => props.selectedFiles.reduce((sum, file) => sum + file.size, 0));
const summaryText = computed(() => (
  props.selectedFiles.length
    ? `已选 ${props.selectedFiles.length} 个文件，合计 ${formatBytes(totalSize.value)}`
    : "支持 PDF / TXT / MD，多选后会保留当前队列。"
));
</script>

<template>
  <div class="upload-section">
    <div class="panel-heading panel-heading--compact">
      <span class="eyebrow">Upload</span>
      <h2>知识源文件</h2>
      <p>{{ summaryText }}</p>
    </div>
    <button class="drop-zone" type="button" @click="emit('pickFiles')" @drop.prevent="emit('dropFiles', $event)" @dragover.prevent>
      <span class="drop-icon">📄</span>
      <p>点击选择，或把文件拖到这里</p>
      <p class="drop-hint">拖拽后可继续追加，适合批量整理资料</p>
    </button>
    <div v-if="selectedFiles.length" class="file-summary">
      已选择 {{ selectedFiles.length }} 个文件，总大小 {{ formatBytes(totalSize) }}
    </div>
    <ul v-if="selectedFiles.length" class="file-list">
      <li v-for="file in selectedFiles" :key="file.path">
        <div class="file-row">
          <span class="file-name">{{ file.name }}</span>
          <span class="file-size">{{ formatBytes(file.size) }}</span>
        </div>
        <button type="button" class="file-remove-btn" @click="emit('removeFile', file.path)">移除</button>
      </li>
    </ul>
  </div>
</template>
