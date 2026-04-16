import { flushPromises, mount } from "@vue/test-utils";
import App from "./App.vue";
import type { RelationGraphApi } from "./types";

const providerStatus = {
  providerMode: "ark",
  localRuntimeStatus: "stopped",
  localModelName: null,
  localModelDir: null,
  detail: "stopped",
  preferredLocalModel: "qwen3.5:9b",
  availableLocalModels: [],
  localModelCandidates: ["qwen3.5:9b", "qwen3.5:4b"]
} as const;

function installMockApi(overrides: Partial<RelationGraphApi> = {}) {
  window.relationGraph = {
    getProviderStatus: vi.fn().mockResolvedValue(providerStatus),
    selectExistingModelDir: vi.fn().mockResolvedValue(providerStatus),
    downloadAndConfigureModels: vi.fn().mockResolvedValue(providerStatus),
    ensureLocalRuntimeStarted: vi.fn().mockResolvedValue(providerStatus),
    setPreferredLocalModel: vi.fn().mockResolvedValue(providerStatus),
    pickInputFiles: vi.fn().mockResolvedValue([
      { path: "E:/demo.txt", name: "demo.txt", size: 1024 }
    ]),
    submitJob: vi.fn().mockResolvedValue({
      jobId: "job-1",
      status: "queued",
      providerMode: "ark",
      detail: "queued",
      currentStage: "queued",
      totalChunks: 0,
      completedChunks: 0
    }),
    getJobStatus: vi.fn(),
    openRunArtifact: vi.fn(),
    exportStandaloneGraph: vi.fn(),
    toFileUrl: vi.fn().mockResolvedValue("file:///demo.html"),
    shutdownBackend: vi.fn(),
    ...overrides
  };
}

describe("App", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it("switches to cloud mode and requires api key before submit", async () => {
    installMockApi();
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.findAll(".provider-switch__btn")[1].trigger("click");
    await wrapper.get(".drop-zone").trigger("click");
    await flushPromises();
    await wrapper.get(".primary-btn").trigger("click");

    expect(wrapper.text()).toContain("请先填写火山方舟 API Key");
  });

  it("picks files and renders the file summary", async () => {
    installMockApi();
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get(".drop-zone").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("demo.txt");
    expect(wrapper.text()).toContain("已选择 1 个文件");
  });

  it("keeps a specific startup status instead of overwriting it with the generic prompt", async () => {
    installMockApi({
      getProviderStatus: vi.fn().mockResolvedValue({
        ...providerStatus,
        providerMode: "local",
        localRuntimeStatus: "missing",
        detail: "本地模型目录未配置，请先下载模型并完成配置。"
      })
    });
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.text()).toContain("本地模型目录未配置，请先下载模型并完成配置。");
    expect(wrapper.text()).not.toContain("请选择文件并开始生成图谱。");
  });

  it("shows backend startup errors instead of falling back to the generic prompt", async () => {
    installMockApi({
      getProviderStatus: vi.fn().mockRejectedValue(new Error("Python backend 启动失败：端口不可用"))
    });
    const wrapper = mount(App);
    await flushPromises();

    expect(wrapper.text()).toContain("Python backend 启动失败：端口不可用");
    expect(wrapper.text()).not.toContain("请选择文件并开始生成图谱。");
  });

  it("renders detailed metadata and warning details after a successful run", async () => {
    installMockApi({
      getProviderStatus: vi.fn().mockResolvedValue({
        ...providerStatus,
        providerMode: "local",
        localRuntimeStatus: "ready",
        detail: "本地ollama已就绪。"
      }),
      submitJob: vi.fn().mockResolvedValue({
        jobId: "job-1",
        status: "succeeded",
        providerMode: "local",
        detail: "图谱生成完成。",
        currentStage: "completed",
        totalChunks: 1,
        completedChunks: 1,
        result: {
          runId: "run-1",
          providerMode: "local",
          runDir: "E:/runs/run-1",
          graphFilePath: "E:/runs/run-1/graph.html",
          graphDataFilePath: "E:/runs/run-1/graph_data.js",
          standaloneGraphFilePath: "E:/runs/run-1/standalone_graph.html",
          chunksCsvFilePath: "E:/runs/run-1/chunks.csv",
          graphCsvFilePath: "E:/runs/run-1/graph.csv",
          groupedGraphCsvFilePath: "E:/runs/run-1/grouped_graph.csv",
          metadataFilePath: "E:/runs/run-1/metadata.json",
          metadata: {
            run_id: "run-1",
            provider: "local",
            model: "qwen3.5:9b",
            input_files: ["demo.txt"],
            chunk_count: 2,
            raw_edge_count: 11,
            final_edge_count: 8,
            node_count: 6,
            community_count: 2,
            artifact_mode: "offline",
            render_data_file: "graph_data.js",
            standalone_graph_file: "standalone_graph.html",
            token_usage: {
              prompt_tokens: 100,
              completion_tokens: 30,
              total_tokens: 130
            },
            source_file_count: 1,
            successful_chunk_count: 1,
            failed_chunk_count: 1,
            warnings: [],
            warning_details: [
              {
                source: "demo.txt",
                page: null,
                chunk_index: 1,
                chunk_id: "chunk-1",
                error: "提取失败"
              }
            ],
            artifact_version: 3,
            edge_label_mode: "primary_with_variants"
          }
        }
      })
    });
    const wrapper = mount(App);
    await flushPromises();

    await wrapper.get(".drop-zone").trigger("click");
    await flushPromises();
    await wrapper.get(".primary-btn").trigger("click");
    await flushPromises();
    await wrapper.get(".result-details").trigger("toggle");

    expect(wrapper.text()).toContain("运行 ID");
    expect(wrapper.text()).toContain("共有 1 个文本块抽取失败");
    expect(wrapper.text()).toContain("demo.txt / 块 1（chunk-1）：提取失败");
    expect(wrapper.text()).toContain("Total Tokens: 130");
  });
});
