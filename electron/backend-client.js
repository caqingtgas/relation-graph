const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const { spawn } = require("node:child_process");
const path = require("node:path");

class BackendClient extends EventEmitter {
  constructor(options = {}) {
    super();
    this.port = options.port || 8765;
    this.host = options.host || "127.0.0.1";
    this.projectRoot = options.projectRoot;
    this.isPackaged = Boolean(options.isPackaged);
    this.backendProcess = null;
    this.startPromise = null;
  }

  get baseUrl() {
    return `http://${this.host}:${this.port}`;
  }

  async start() {
    if (this.startPromise) {
      return this.startPromise;
    }
    this.startPromise = this.#startInternal().finally(() => {
      this.startPromise = null;
    });
    return this.startPromise;
  }

  async #startInternal() {
    if (await this.#isHealthy()) {
      return;
    }

    const command = this.isPackaged ? this.#packagedCommand() : this.#devCommand();
    this.backendProcess = spawn(command.file, command.args, {
      cwd: command.cwd,
      env: {
        ...process.env,
        RELATION_GRAPH_PROJECT_ROOT: this.projectRoot
      },
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"]
    });

    this.backendProcess.stdout?.on("data", (chunk) => {
      this.emit("stdout", chunk.toString());
    });
    this.backendProcess.stderr?.on("data", (chunk) => {
      this.emit("stderr", chunk.toString());
    });
    this.backendProcess.once("exit", (code) => {
      this.emit("backend-exit", { code });
      this.backendProcess = null;
    });
    this.backendProcess.once("error", (error) => {
      this.emit("backend-error", { detail: error.message });
    });

    await this.#waitForHealth();
  }

  async stop() {
    const processRef = this.backendProcess;
    this.backendProcess = null;
    if (!processRef) {
      return;
    }
    processRef.kill();
  }

  async invoke(method, payload = undefined) {
    const route = this.#routeFor(method, payload);
    return this.#request(route.path, {
      method: route.method,
      body: route.method === "GET" || payload === undefined ? undefined : JSON.stringify(payload)
    });
  }

  async #request(pathname, init = {}) {
    const response = await fetch(`${this.baseUrl}${pathname}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init.headers || {})
      }
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || `Backend request failed: ${pathname}`);
    }
    return payload;
  }

  #routeFor(method, payload) {
    const routes = {
      "provider.status": { method: "GET", path: "/provider/status" },
      "provider.bind_model_dir": { method: "POST", path: "/provider/bind-model-dir" },
      "provider.download_models": { method: "POST", path: "/provider/download-models" },
      "provider.ensure_started": { method: "POST", path: "/provider/ensure-started" },
      "provider.set_preferred_model": { method: "POST", path: "/provider/preferred-model" },
      "job.submit": { method: "POST", path: "/jobs" },
      "job.status": { method: "GET", path: null }
    };
    const route = routes[method];
    if (!route) {
      throw new Error(`Unsupported backend method: ${method}`);
    }
    if (method === "job.status") {
      return { method: "GET", path: `/jobs/${encodeURIComponent(String((payload || {}).job_id || ""))}` };
    }
    return route;
  }

  #packagedCommand() {
    const cwd = path.join(process.resourcesPath, "backend");
    return {
      file: path.join(cwd, "relation-graph-backend.exe"),
      args: [],
      cwd
    };
  }

  #devCommand() {
    const configuredPython = process.env.RELATION_GRAPH_DEV_PYTHON || process.env.RELATION_GRAPH_PYTHON;
    if (configuredPython) {
      return {
        file: configuredPython,
        args: ["-m", "relation_graph.run_desktop_backend"],
        cwd: this.projectRoot
      };
    }

    if (process.platform === "win32") {
      const activeEnvironmentCandidates = [
        process.env.VIRTUAL_ENV ? path.join(process.env.VIRTUAL_ENV, "Scripts", "python.exe") : null,
        process.env.CONDA_PYTHON_EXE || null,
        process.env.CONDA_PREFIX ? path.join(process.env.CONDA_PREFIX, "python.exe") : null
      ].filter(Boolean);
      for (const candidate of activeEnvironmentCandidates) {
        if (fs.existsSync(candidate)) {
          return {
            file: candidate,
            args: ["-m", "relation_graph.run_desktop_backend"],
            cwd: this.projectRoot
          };
        }
      }

      const repoVenvCandidates = [
        path.join(this.projectRoot, ".venv", "Scripts", "python.exe"),
        path.join(this.projectRoot, "venv", "Scripts", "python.exe"),
        path.join(this.projectRoot, ".build-tools", "backend-packager", "Scripts", "python.exe")
      ];
      for (const candidate of repoVenvCandidates) {
        if (fs.existsSync(candidate)) {
          return {
            file: candidate,
            args: ["-m", "relation_graph.run_desktop_backend"],
            cwd: this.projectRoot
          };
        }
      }

      const pyLauncher = path.join(process.env.SystemRoot || "C:\\Windows", "py.exe");
      if (fs.existsSync(pyLauncher)) {
        return {
          file: pyLauncher,
          args: ["-3", "-m", "relation_graph.run_desktop_backend"],
          cwd: this.projectRoot
        };
      }

      const userPython = path.join(process.env.LOCALAPPDATA || "", "Python", "bin", "python.exe");
      if (fs.existsSync(userPython)) {
        return {
          file: userPython,
          args: ["-m", "relation_graph.run_desktop_backend"],
          cwd: this.projectRoot
        };
      }

      throw new Error("未找到可用的开发 Python，请设置 RELATION_GRAPH_DEV_PYTHON。");
    }

    const unixCandidates = [
      process.env.VIRTUAL_ENV ? path.join(process.env.VIRTUAL_ENV, "bin", "python") : null,
      path.join(this.projectRoot, ".venv", "bin", "python"),
      path.join(this.projectRoot, "venv", "bin", "python"),
      path.join(this.projectRoot, ".build-tools", "backend-packager", "bin", "python")
    ].filter(Boolean);
    for (const candidate of unixCandidates) {
      if (fs.existsSync(candidate)) {
        return {
          file: candidate,
          args: ["-m", "relation_graph.run_desktop_backend"],
          cwd: this.projectRoot
        };
      }
    }

    throw new Error("未找到可用的开发 Python，请设置 RELATION_GRAPH_DEV_PYTHON。");
  }

  async #waitForHealth(timeoutMs = 20000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (await this.#isHealthy()) {
        return;
      }
      if (this.backendProcess && this.backendProcess.exitCode !== null) {
        throw new Error(`Python backend exited with code ${this.backendProcess.exitCode}`);
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    throw new Error("Timed out waiting for Python backend health check.");
  }

  async #isHealthy() {
    try {
      const response = await fetch(`${this.baseUrl}/health`);
      return response.ok;
    } catch {
      return false;
    }
  }
}

module.exports = {
  BackendClient
};
