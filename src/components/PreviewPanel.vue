<script setup lang="ts">
defineProps<{
  previewUrl: string;
  graphFilePath: string | null;
  standaloneGraphFilePath: string | null;
}>();

const emit = defineEmits<{
  openArtifact: [string];
  exportStandaloneGraph: [];
}>();
</script>

<template>
  <main class="viewer">
    <div class="viewer-header">
      <div>
        <span class="eyebrow">Preview</span>
        <span class="viewer-title">图谱可视化预览</span>
      </div>
      <div class="viewer-actions">
        <button
          v-if="standaloneGraphFilePath"
          class="icon-btn"
          type="button"
          title="保存可打开图谱文件"
          @click="emit('exportStandaloneGraph')"
        >
          ⤓
        </button>
        <button
          v-if="graphFilePath"
          class="icon-btn"
          type="button"
          title="在系统默认应用中打开"
          @click="emit('openArtifact', graphFilePath)"
        >
          ↗
        </button>
      </div>
    </div>
    <div class="iframe-container">
      <div v-if="!previewUrl" class="iframe-placeholder">
        <strong>等待结果生成</strong>
        <span>完成后这里会展示可交互的动态关系图谱。</span>
      </div>
      <iframe v-else id="graphFrame" :src="previewUrl" title="图谱预览"></iframe>
    </div>
  </main>
</template>
