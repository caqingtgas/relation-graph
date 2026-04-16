<script setup lang="ts">
import type { DesktopInputFile } from "../types";
import { formatBytes } from "../utils/format";

defineProps<{
  selectedFiles: DesktopInputFile[];
}>();

const emit = defineEmits<{
  pickFiles: [];
  removeFile: [string];
  dropFiles: [DragEvent];
}>();
</script>

<template>
  <div class="upload-section">
    <label class="label">知识源文件</label>
    <button class="drop-zone" type="button" @click="emit('pickFiles')" @drop.prevent="emit('dropFiles', $event)" @dragover.prevent>
      <span class="drop-icon">📄</span>
      <p>点击选择或将文件拖拽到此处</p>
      <p class="drop-hint">支持 .pdf, .txt, .md (可多选)</p>
    </button>
    <div v-if="selectedFiles.length" class="file-summary">
      已选择 {{ selectedFiles.length }} 个文件，总大小 {{ formatBytes(selectedFiles.reduce((sum, file) => sum + file.size, 0)) }}
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
