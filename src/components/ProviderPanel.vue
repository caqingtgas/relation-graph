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
}>();

const emit = defineEmits<{
  "update:selectedProvider": [ProviderPreference];
  "update:selectedLocalModel": [string];
  "update:apiKey": [string];
  "update:rememberApiKey": [boolean];
  "update:model": [string];
  downloadAndConfigureModels: [];
  selectExistingModelDir: [];
  changePreferredLocalModel: [];
}>();

const localPanelVisible = computed(() => props.selectedProvider === "local");
const providerBadge = computed(() => getProviderBadge(props.providerStatus));
const providerBadgeClass = computed(() => (
  props.providerStatus?.localRuntimeStatus === "ready" ? "provider-badge--ready" : "provider-badge--not-ready"
));
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
    <div class="panel-heading">
      <p>适合需要离线执行、文件留在本机的场景。</p>
    </div>
    <section class="provider-panel">
      <div class="provider-panel__header">
        <span class="provider-panel__title">本地接口配置</span>
        <span class="provider-badge" :class="providerBadgeClass">
          {{ providerBadge }}
        </span>
      </div>
      <div class="provider-panel__body">
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

        <div class="provider-field">
          <label class="provider-panel__label" for="localModelSelect">选择模型</label>
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
        </div>
        <div class="provider-panel__actions">
          <button class="secondary-btn" type="button" :disabled="isLoading" @click="emit('downloadAndConfigureModels')">
            下载模型并配置目录
          </button>
          <button class="secondary-btn" type="button" :disabled="isLoading" @click="emit('selectExistingModelDir')">
            已有模型并配置目录
          </button>
        </div>
      </div>
    </section>
  </section>

  <section v-else class="mode-panel">
    <div class="panel-heading">
      <p>填写密钥后即可调用火山方舟，不影响本地配置。</p>
    </div>
    <section class="provider-panel">
      <div class="provider-panel__header">
        <span class="provider-panel__title">云端接口配置</span>
      </div>
      <div class="provider-panel__body">
        <div class="provider-field">
          <label class="provider-panel__label" for="apiKey">火山方舟 API Key</label>
          <input
            id="apiKey"
            class="input"
            type="password"
            placeholder="输入火山方舟接口密钥"
            :value="apiKey"
            @input="emit('update:apiKey', ($event.target as HTMLInputElement).value)"
          >
        </div>
        <label class="remember-row">
          <input
            :checked="rememberApiKey"
            type="checkbox"
            @change="emit('update:rememberApiKey', ($event.target as HTMLInputElement).checked)"
          >
          <span>记住密钥（否则仅保存在当前会话）</span>
        </label>
        <p class="provider-note">{{ cloudHint }}</p>

        <div class="provider-field">
          <label class="provider-panel__label" for="model">Model ID</label>
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
  </section>
</template>
