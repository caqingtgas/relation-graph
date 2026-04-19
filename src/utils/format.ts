import type { JobMetadata, ProviderStatus, WarningDetail } from "../types";

const PATH_PATTERN = /([A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n，。；；、,]*)/g;

export function formatBytes(value: number) {
  return `${(value / 1024 / 1024).toFixed(2)} MB`;
}

export function escapeHtml(value: string) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function formatPathLikeHtml(value: string | null | undefined) {
  const escaped = escapeHtml(value || "");
  return escaped.replace(PATH_PATTERN, '<span class="path-inline">$1</span>');
}

export function isSupportedFileName(fileName: string) {
  const normalized = fileName.trim().toLowerCase();
  return normalized.endsWith(".pdf") || normalized.endsWith(".txt") || normalized.endsWith(".md");
}

export function getProviderBadge(status: ProviderStatus | null) {
  return status?.localRuntimeStatus === "ready" ? "就位" : "未就位";
}

export function getCloudHint(status: ProviderStatus | null) {
  if (status?.localRuntimeStatus === "ready") {
    return "云端模式下将直接使用火山方舟；本地模式已可用时，可随时切回本地。";
  }
  return "云端模式下将直接使用火山方舟。密钥只保存在当前桌面应用，不会写入结果文件。";
}

export function getLocalModelOptions(status: ProviderStatus | null) {
  const candidates = status?.localModelCandidates?.length ? status.localModelCandidates : ["qwen3.5:9b", "qwen3.5:4b"];
  const available = new Set(status?.availableLocalModels || []);
  return candidates.map((modelId) => ({
    value: modelId,
    label: available.has(modelId) ? modelId : `${modelId}（未就绪）`
  }));
}

export function formatWarningDetail(item: WarningDetail) {
  const location = [
    item.source || "未知来源",
    item.page != null ? `第 ${item.page} 页` : null,
    `块 ${item.chunk_index}`
  ]
    .filter(Boolean)
    .join(" / ");
  return `${location}（${item.chunk_id}）：${item.error}`;
}

export function buildWarningSummary(metadata: JobMetadata) {
  if (metadata.warning_details.length > 0) {
    return `共有 ${metadata.failed_chunk_count} 个文本块抽取失败，以下是具体位置。`;
  }
  if (metadata.warnings.length > 0) {
    return `共有 ${metadata.warnings.length} 条抽取警告。`;
  }
  return "";
}

export function buildWarningItems(metadata: JobMetadata) {
  if (metadata.warning_details.length > 0) {
    return metadata.warning_details.map(formatWarningDetail);
  }
  return metadata.warnings;
}

export function buildMetaInfoText(runId: string, metadata: JobMetadata, fallbackModel: string) {
  const usage = metadata.token_usage;
  const provider = metadata.provider === "local" ? "LOCAL" : "ARK";
  return [
    `运行 ID: ${runId}`,
    `实际提供商: ${provider}`,
    `使用模型: ${metadata.model || fallbackModel}`,
    `源文件数: ${metadata.source_file_count}`,
    `解析块数: ${metadata.chunk_count} 个`,
    `成功块数: ${metadata.successful_chunk_count}`,
    `失败块数: ${metadata.failed_chunk_count}`,
    `提取节点: ${metadata.node_count} 个`,
    `最终关系: ${metadata.final_edge_count} 条`,
    `社区分组: ${metadata.community_count} 个`,
    `Prompt Tokens: ${usage.prompt_tokens}`,
    `Completion Tokens: ${usage.completion_tokens}`,
    `Total Tokens: ${usage.total_tokens}`
  ].join("\n");
}
