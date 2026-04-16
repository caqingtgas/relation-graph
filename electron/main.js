const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { BackendClient } = require("./backend-client.js");

const projectRoot = app.isPackaged ? path.dirname(process.execPath) : app.getAppPath();
const backend = new BackendClient({
  projectRoot,
  isPackaged: app.isPackaged
});
let backendStartupError = null;

function mapProviderStatus(payload) {
  return {
    providerMode: payload.provider_mode,
    localRuntimeStatus: payload.local_runtime_status,
    localModelName: payload.local_model_name,
    localModelDir: payload.local_model_dir,
    detail: payload.detail,
    preferredLocalModel: payload.preferred_local_model,
    availableLocalModels: payload.available_local_models || [],
    localModelCandidates: payload.local_model_candidates || []
  };
}

function mapJobMetadata(metadata = {}) {
  return {
    run_id: metadata.run_id || "",
    provider: metadata.provider || "ark",
    model: metadata.model || "",
    input_files: metadata.input_files || [],
    chunk_count: Number(metadata.chunk_count || 0),
    raw_edge_count: Number(metadata.raw_edge_count || 0),
    final_edge_count: Number(metadata.final_edge_count || 0),
    node_count: Number(metadata.node_count || 0),
    community_count: Number(metadata.community_count || 0),
    artifact_mode: metadata.artifact_mode || "",
    render_data_file: metadata.render_data_file || "",
    standalone_graph_file: metadata.standalone_graph_file || "",
    token_usage: {
      prompt_tokens: Number(metadata.token_usage?.prompt_tokens || 0),
      completion_tokens: Number(metadata.token_usage?.completion_tokens || 0),
      total_tokens: Number(metadata.token_usage?.total_tokens || 0)
    },
    source_file_count: Number(metadata.source_file_count || 0),
    successful_chunk_count: Number(metadata.successful_chunk_count || 0),
    failed_chunk_count: Number(metadata.failed_chunk_count || 0),
    warnings: metadata.warnings || [],
    warning_details: metadata.warning_details || [],
    artifact_version: Number(metadata.artifact_version || 0),
    edge_label_mode: metadata.edge_label_mode || ""
  };
}

function mapJobResult(result) {
  if (!result) {
    return null;
  }
  return {
    runId: result.run_id,
    providerMode: result.provider_mode,
    runDir: result.runDir,
    graphFilePath: result.graphFilePath,
    graphDataFilePath: result.graphDataFilePath,
    standaloneGraphFilePath: result.standaloneGraphFilePath,
    chunksCsvFilePath: result.chunksCsvFilePath,
    graphCsvFilePath: result.graphCsvFilePath,
    groupedGraphCsvFilePath: result.groupedGraphCsvFilePath,
    metadataFilePath: result.metadataFilePath,
    metadata: mapJobMetadata(result.metadata)
  };
}

function mapJobPayload(payload) {
  return {
    jobId: payload.job_id,
    status: payload.status,
    providerMode: payload.provider_mode,
    createdAt: payload.created_at,
    startedAt: payload.started_at,
    finishedAt: payload.finished_at,
    totalChunks: payload.total_chunks,
    completedChunks: payload.completed_chunks,
    currentStage: payload.current_stage,
    detail: payload.detail,
    queuePosition: payload.queue_position,
    statusUrl: payload.status_url,
    result: mapJobResult(payload.result)
  };
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1360,
    height: 920,
    minWidth: 900,
    minHeight: 760,
    backgroundColor: "#f0f4f8",
    webPreferences: {
      preload: path.join(app.getAppPath(), "electron", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  });

  if (process.env.VITE_DEV_SERVER_URL) {
    window.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    window.loadFile(path.join(app.getAppPath(), "dist", "index.html"));
  }
}

function registerIpcHandlers() {
  ipcMain.handle("relation-graph:getProviderStatus", async () => {
    if (backendStartupError) {
      throw new Error(backendStartupError);
    }
    return mapProviderStatus(await backend.invoke("provider.status"));
  });
  ipcMain.handle("relation-graph:pickInputFiles", async () => {
    const result = await dialog.showOpenDialog({
      properties: ["openFile", "multiSelections"],
      filters: [{ name: "Documents", extensions: ["pdf", "txt", "md"] }]
    });
    if (result.canceled) {
      return [];
    }
    return result.filePaths.map((filePath) => {
      const stats = fs.statSync(filePath);
      return {
        path: filePath,
        name: path.basename(filePath),
        size: stats.size
      };
    });
  });
  ipcMain.handle("relation-graph:selectExistingModelDir", async () => {
    const result = await dialog.showOpenDialog({ properties: ["openDirectory"] });
    if (result.canceled || result.filePaths.length === 0) {
      throw new Error("未选择目录。");
    }
    return mapProviderStatus(await backend.invoke("provider.bind_model_dir", { model_dir: result.filePaths[0] }));
  });
  ipcMain.handle("relation-graph:downloadAndConfigureModels", async () => {
    const result = await dialog.showOpenDialog({ properties: ["openDirectory", "createDirectory"] });
    if (result.canceled || result.filePaths.length === 0) {
      throw new Error("未选择目录。");
    }
    return mapProviderStatus(await backend.invoke("provider.download_models", { model_dir: result.filePaths[0] }));
  });
  ipcMain.handle("relation-graph:ensureLocalRuntimeStarted", async () => mapProviderStatus(await backend.invoke("provider.ensure_started")));
  ipcMain.handle("relation-graph:setPreferredLocalModel", (_, modelName) =>
    backend.invoke("provider.set_preferred_model", { model_name: modelName }).then(mapProviderStatus)
  );
  ipcMain.handle("relation-graph:submitJob", async (_, payload) => mapJobPayload(await backend.invoke("job.submit", payload)));
  ipcMain.handle("relation-graph:getJobStatus", async (_, jobId) => mapJobPayload(await backend.invoke("job.status", { job_id: jobId })));
  ipcMain.handle("relation-graph:openRunArtifact", async (_, targetPath) => {
    const errorMessage = await shell.openPath(targetPath);
    if (errorMessage) {
      throw new Error(errorMessage);
    }
    return targetPath;
  });
  ipcMain.handle("relation-graph:exportStandaloneGraph", async (_, sourcePath, destinationPath) => {
    let finalPath = destinationPath;
    if (!finalPath) {
      const result = await dialog.showSaveDialog({
        defaultPath: path.basename(sourcePath),
        filters: [{ name: "HTML", extensions: ["html"] }]
      });
      if (result.canceled || !result.filePath) {
        throw new Error("未选择导出路径。");
      }
      finalPath = result.filePath;
    }
    fs.copyFileSync(sourcePath, finalPath);
    return finalPath;
  });
  ipcMain.handle("relation-graph:fileUrl", (_, filePath) => pathToFileURL(filePath).toString());
  ipcMain.handle("relation-graph:shutdownBackend", () => backend.stop());
}

app.whenReady().then(async () => {
  if (!process.env.VITE_DEV_SERVER_URL) {
    process.env.VITE_DEV_SERVER_URL = "";
  }
  registerIpcHandlers();
  try {
    await backend.start();
    backendStartupError = null;
  } catch (error) {
    backendStartupError = `Python backend 启动失败：${error.message}`;
    console.error("Failed to start Python backend", error);
  }
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", async () => {
  await backend.stop();
  if (process.platform !== "darwin") {
    app.quit();
  }
});
