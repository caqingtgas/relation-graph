const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("relationGraph", {
  getProviderStatus: (options) => ipcRenderer.invoke("relation-graph:getProviderStatus", options),
  pickInputFiles: () => ipcRenderer.invoke("relation-graph:pickInputFiles"),
  selectExistingModelDir: () => ipcRenderer.invoke("relation-graph:selectExistingModelDir"),
  downloadAndConfigureModels: () => ipcRenderer.invoke("relation-graph:downloadAndConfigureModels"),
  setPreferredLocalModel: (modelName) => ipcRenderer.invoke("relation-graph:setPreferredLocalModel", modelName),
  submitJob: (payload) => ipcRenderer.invoke("relation-graph:submitJob", payload),
  getJobStatus: (jobId) => ipcRenderer.invoke("relation-graph:getJobStatus", jobId),
  openRunArtifact: (targetPath) => ipcRenderer.invoke("relation-graph:openRunArtifact", targetPath),
  exportStandaloneGraph: (sourcePath, destinationPath) =>
    ipcRenderer.invoke("relation-graph:exportStandaloneGraph", sourcePath, destinationPath),
  toPreviewUrl: (filePath) => ipcRenderer.invoke("relation-graph:previewUrl", filePath),
  toFileUrl: (filePath) => ipcRenderer.invoke("relation-graph:fileUrl", filePath),
  shutdownDesktopWorker: () => ipcRenderer.invoke("relation-graph:shutdownDesktopWorker")
});
