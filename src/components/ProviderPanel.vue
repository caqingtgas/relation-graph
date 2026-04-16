<script setup lang="ts">
import { computed } from "vue";
import type { ProviderPreference, ProviderStatus } from "../types";
import { formatPathLikeHtml, getCloudHint, getLocalModelOptions, getProviderBadge } from "../utils/format";

const props = defineProps<{
  selectedProvider: ProviderPreference;
  providerStatus: ProviderStatus | null;
  selectedLocalModel: string;
  apiKey: string;
  rememberApiKey: boolean;
  model: string;
  isLoading: boolean;
  canStartLocalRuntime: boolean;
  canLaunchLocalRuntimeTerminal: boolean;
}>();

const emit = defineEmits<{
  "update:selectedProvider": [ProviderPreference];
  "update:selectedLocalModel": [string];
  "update:apiKey": [string];
  "update:rememberApiKey": [boolean];
  "update:model": [string];
  startLocalRuntime: [];
  launchLocalRuntimeTerminal: [];
  downloadAndConfigureModels: [];
  selectExistingModelDir: [];
  changePreferredLocalModel: [];
}>();

const localPanelVisible = computed(() => props.selectedProvider === "local");
const providerBadge = computed(() => getProviderBadge(props.providerStatus));
const providerDetailHtml = computed(() => formatPathLikeHtml(props.providerStatus?.detail || "正在检测本地ollama..."));
const modelDirHtml = computed(() => formatPathLikeHtml(props.providerStatus?.localModelDir || "尚未配置"));
const cloudHint = computed(() => getCloudHint(props.providerStatus));
const modelOptions = computed(() => getLocalModelOptions(props.providerStatus));
</script>

<template>
  <section class="provider-switch">
    <button
      class="provider-switch__btn"
      :class="{ 'provider-switch__btn--active': selectedProvider === 'local' }"
      type="button"
      @click="emit('update:selectedProvider', 'local')"
    >
      本地
    </button>
    <button
      class="provider-switch__btn"
      :class="{ 'provider-switch__btn--active': selectedProvider === 'ark' }"
      type="button"
      @click="emit('update:selectedProvider', 'ark')"
    >
      云端
    </button>
  </section>

  <section v-if="localPanelVisible" class="mode-panel">
    <div class="local-actions">
      <button
        v-if="canStartLocalRuntime"
        class="secondary-btn"
        type="button"
        :disabled="isLoading"
        @click="emit('startLocalRuntime')"
      >
        启动本地引擎
      </button>
      <button
        v-if="canLaunchLocalRuntimeTerminal"
        class="secondary-btn"
        type="button"
        :disabled="isLoading"
        @click="emit('launchLocalRuntimeTerminal')"
      >
        手动启动终端
      </button>
      <button class="secondary-btn" type="button" :disabled="isLoading" @click="emit('downloadAndConfigureModels')">
        下载模型并配置目录
      </button>
      <button class="secondary-btn" type="button" :disabled="isLoading" @click="emit('selectExistingModelDir')">
        已有模型并配置目录
      </button>
    </div>

    <section class="provider-panel">
      <div class="provider-panel__header">
        <span class="provider-panel__title">本地路线状态</span>
        <span
          class="provider-badge"
          :class="providerStatus?.providerMode === 'local' ? 'provider-badge--local' : 'provider-badge--ark'"
        >
          {{ providerBadge }}
        </span>
      </div>
      <p class="provider-panel__detail" v-html="providerDetailHtml"></p>
      <div class="provider-panel__meta">
        <div>
          <span class="provider-panel__label">当前模型</span>
          <span class="provider-panel__value">{{ providerStatus?.localModelName || "未检测到" }}</span>
        </div>
        <div>
          <span class="provider-panel__label">模型目录</span>
          <span id="localModelDir" class="provider-panel__value" v-html="modelDirHtml"></span>
        </div>
      </div>

      <label class="label" for="localModelSelect">模型切换</label>
      <select
        id="localModelSelect"
        class="input"
        :value="selectedLocalModel"
        :disabled="isLoading || modelOptions.length === 0"
        @change="emit('update:selectedLocalModel', ($event.target as HTMLSelectElement).value); emit('changePreferredLocalModel')"
      >
        <option v-for="option in modelOptions" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </select>
      <p class="config-hint config-hint--field-note">切换的是本地优先模型；如果当前目录尚未识别到对应模型，会自动保持现状。</p>
    </section>
  </section>

  <section v-else class="mode-panel">
    <div class="config-panel">
      <div class="config-panel__heading">云端接口配置</div>
      <div class="config-content">
        <label class="label" for="apiKey">火山方舟 API Key</label>
        <input
          id="apiKey"
          class="input"
          type="password"
          placeholder="输入火山方舟接口密钥"
          :value="apiKey"
          @input="emit('update:apiKey', ($event.target as HTMLInputElement).value)"
        >
        <label class="remember-row">
          <input
            :checked="rememberApiKey"
            type="checkbox"
            @change="emit('update:rememberApiKey', ($event.target as HTMLInputElement).checked)"
          >
          <span>记住密钥（否则仅保存在当前会话）</span>
        </label>
        <p class="config-hint">{{ cloudHint }}</p>

        <label class="label" for="model">Ark 模型标识</label>
        <input
          id="model"
          class="input"
          type="text"
          :value="model"
          @input="emit('update:model', ($event.target as HTMLInputElement).value)"
        >
      </div>
    </div>
  </section>
</template>
