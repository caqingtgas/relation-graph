import type { ProviderPreference } from "../types";

export interface SavedConfig {
  provider: ProviderPreference;
  apiKey: string;
  rememberApiKey: boolean;
  model: string;
}

export function loadConfig(defaultModel: string): SavedConfig {
  const remembered = localStorage.getItem("ark_remember_api_key") === "true";
  return {
    rememberApiKey: remembered,
    provider: localStorage.getItem("provider_mode_preference") === "ark" ? "ark" : "local",
    model: localStorage.getItem("ark_model_id") || defaultModel,
    apiKey: remembered ? localStorage.getItem("ark_api_key") || "" : sessionStorage.getItem("ark_api_key") || ""
  };
}

export function saveConfig(config: SavedConfig) {
  sessionStorage.setItem("ark_api_key", config.apiKey.trim());
  localStorage.setItem("provider_mode_preference", config.provider);
  localStorage.setItem("ark_model_id", config.model.trim());
  if (config.rememberApiKey && config.apiKey.trim()) {
    localStorage.setItem("ark_api_key", config.apiKey.trim());
    localStorage.setItem("ark_remember_api_key", "true");
    return;
  }
  localStorage.removeItem("ark_api_key");
  localStorage.removeItem("ark_remember_api_key");
}
