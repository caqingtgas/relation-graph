export type ProviderPreference = "local" | "ark";

export interface DesktopInputFile {
  path: string;
  name: string;
  size: number;
}

export interface ProviderStatus {
  providerMode: ProviderPreference | string;
  localRuntimeStatus: string;
  localModelName: string | null;
  localModelDir: string | null;
  detail: string;
  preferredLocalModel: string | null;
  availableLocalModels: string[];
  localModelCandidates: string[];
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface WarningDetail {
  source: string;
  page: number | null;
  chunk_index: number;
  chunk_id: string;
  error: string;
}

export interface JobMetadata {
  run_id: string;
  provider: string;
  model: string;
  input_files: string[];
  chunk_count: number;
  raw_edge_count: number;
  final_edge_count: number;
  node_count: number;
  community_count: number;
  artifact_mode: string;
  render_data_file: string;
  standalone_graph_file: string;
  token_usage: TokenUsage;
  source_file_count: number;
  successful_chunk_count: number;
  failed_chunk_count: number;
  warnings: string[];
  warning_details: WarningDetail[];
  artifact_version: number;
  edge_label_mode: string;
}

export interface JobResult {
  runId: string;
  providerMode: ProviderPreference | string;
  runDir: string;
  graphFilePath: string;
  graphDataFilePath: string;
  standaloneGraphFilePath: string;
  chunksCsvFilePath: string;
  graphCsvFilePath: string;
  groupedGraphCsvFilePath: string;
  metadataFilePath: string;
  metadata: JobMetadata;
}

export interface JobPayload {
  jobId: string;
  status: string;
  providerMode: string;
  createdAt: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  totalChunks: number;
  completedChunks: number;
  currentStage: string;
  detail: string;
  queuePosition?: number | null;
  result?: JobResult | null;
}

export interface RelationGraphApi {
  getProviderStatus(options?: { autoStart?: boolean }): Promise<ProviderStatus>;
  pickInputFiles(): Promise<DesktopInputFile[]>;
  selectExistingModelDir(): Promise<ProviderStatus>;
  downloadAndConfigureModels(): Promise<ProviderStatus>;
  setPreferredLocalModel(modelName: string): Promise<ProviderStatus>;
  submitJob(payload: {
    api_key: string;
    model: string;
    provider_preference: ProviderPreference;
    files: string[];
  }): Promise<JobPayload>;
  getJobStatus(jobId: string): Promise<JobPayload>;
  openRunArtifact(targetPath: string): Promise<string>;
  exportStandaloneGraph(sourcePath: string, destinationPath?: string): Promise<string>;
  toPreviewUrl(filePath: string): Promise<string>;
  toFileUrl(filePath: string): Promise<string>;
  shutdownDesktopWorker(): Promise<void>;
}

declare global {
  interface Window {
    relationGraph: RelationGraphApi;
  }
}
