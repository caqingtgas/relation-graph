const fs = require("node:fs");
const path = require("node:path");
const { execFileSync, spawn } = require("node:child_process");
const readline = require("node:readline");

const DEV_WORKER_MODULE = "relation_graph.run_desktop_worker";
const DEV_WORKER_PROBE = "import httpx, pydantic, relation_graph.run_desktop_worker";
const DEV_REQUIREMENTS_FILE = "requirements.txt";

class PythonWorkerClient {
  constructor(options = {}) {
    this.projectRoot = options.projectRoot;
    this.isPackaged = Boolean(options.isPackaged);
    this.workerProcess = null;
    this.startPromise = null;
    this.pendingRequests = new Map();
    this.nextRequestId = 1;
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
    if (this.workerProcess && this.workerProcess.exitCode === null) {
      return;
    }

    const command = this.isPackaged ? this.#packagedCommand() : this.#devCommand();
    this.workerProcess = spawn(command.file, command.args, {
      cwd: command.cwd,
      env: {
        ...process.env,
        RELATION_GRAPH_PROJECT_ROOT: this.projectRoot
      },
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"]
    });

    const stdoutReader = readline.createInterface({ input: this.workerProcess.stdout });
    stdoutReader.on("line", (line) => this.#handleStdoutLine(line));
    this.workerProcess.stderr?.on("data", (chunk) => {
      const detail = chunk.toString().trim();
      if (detail) {
        console.error("[relation-graph-worker]", detail);
      }
    });
    this.workerProcess.once("exit", (code) => {
      const error = new Error(`Python worker exited with code ${code}`);
      this.#rejectPendingRequests(error);
      this.workerProcess = null;
    });
    this.workerProcess.once("error", (error) => {
      this.#rejectPendingRequests(error);
    });

    await this.#sendRequest("provider.getStatus", {});
  }

  async stop() {
    const processRef = this.workerProcess;
    this.workerProcess = null;
    if (!processRef) {
      return;
    }
    try {
      await this.#sendRequest("app.shutdown", {}, processRef);
    } catch {
      // 关闭阶段优先释放子进程，不阻塞退出。
    }
    if (processRef.exitCode === null) {
      processRef.kill();
    }
  }

  async invoke(method, params = {}) {
    await this.start();
    return this.#sendRequest(method, params);
  }

  #sendRequest(method, params = {}, processRef = this.workerProcess) {
    if (!processRef || processRef.exitCode !== null || !processRef.stdin) {
      return Promise.reject(new Error("Python worker 未启动。"));
    }

    const id = `req-${this.nextRequestId++}`;
    const payload = JSON.stringify({ id, method, params });
    return new Promise((resolve, reject) => {
      this.pendingRequests.set(id, { resolve, reject });
      processRef.stdin.write(`${payload}\n`, "utf8", (error) => {
        if (error) {
          this.pendingRequests.delete(id);
          reject(error);
        }
      });
    });
  }

  #handleStdoutLine(line) {
    if (!line.trim()) {
      return;
    }

    let payload;
    try {
      payload = JSON.parse(line);
    } catch (error) {
      console.error("Invalid worker response:", line, error);
      return;
    }

    const requestId = payload.id;
    if (!requestId || !this.pendingRequests.has(requestId)) {
      return;
    }
    const pending = this.pendingRequests.get(requestId);
    this.pendingRequests.delete(requestId);

    if (payload.ok) {
      pending.resolve(payload.result);
      return;
    }

    const message = payload.error?.message || "桌面服务返回未知错误。";
    const error = new Error(message);
    error.code = payload.error?.code || "worker_error";
    pending.reject(error);
  }

  #rejectPendingRequests(error) {
    for (const pending of this.pendingRequests.values()) {
      pending.reject(error);
    }
    this.pendingRequests.clear();
  }

  #packagedCommand() {
    const cwd = path.join(process.resourcesPath, "backend");
    return {
      file: path.join(cwd, "relation-graph-worker.exe"),
      args: [],
      cwd
    };
  }

  #buildPythonCommand(file, args = [], label = file) {
    return {
      file,
      bootstrapArgs: [...args],
      args: [...args, "-m", DEV_WORKER_MODULE],
      probeArgs: [...args, "-c", DEV_WORKER_PROBE],
      cwd: this.projectRoot,
      label
    };
  }

  #probeDevCommand(command) {
    try {
      execFileSync(command.file, command.probeArgs, {
        cwd: command.cwd,
        env: {
          ...process.env,
          RELATION_GRAPH_PROJECT_ROOT: this.projectRoot
        },
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"]
      });
      return null;
    } catch (error) {
      const stderr = error.stderr?.toString().trim();
      const stdout = error.stdout?.toString().trim();
      return stderr || stdout || error.message;
    }
  }

  #resolveValidatedDevCommand(candidates) {
    const failures = [];
    for (const candidate of candidates) {
      const detail = this.#probeDevCommand(candidate);
      if (!detail) {
        return candidate;
      }
      failures.push(`${candidate.label}: ${detail}`);
    }

    const summary = failures.slice(0, 3).join(" | ");
    throw new Error(
      `未找到可用的开发 Python，请设置 RELATION_GRAPH_DEV_PYTHON。` +
      (summary ? ` 已检查 ${failures.length} 个候选解释器：${summary}` : "")
    );
  }

  #venvPythonPath(venvDir) {
    if (process.platform === "win32") {
      return path.join(venvDir, "Scripts", "python.exe");
    }
    return path.join(venvDir, "bin", "python");
  }

  #runBootstrapStep(file, args, label) {
    console.log(`[relation-graph-worker] ${label}`);
    execFileSync(file, args, {
      cwd: this.projectRoot,
      env: {
        ...process.env,
        RELATION_GRAPH_PROJECT_ROOT: this.projectRoot
      },
      windowsHide: true,
      stdio: "inherit"
    });
  }

  #bootstrapProjectVenv(baseCommand) {
    const venvDir = path.join(this.projectRoot, ".venv");
    const venvPython = this.#venvPythonPath(venvDir);
    const requirementsFile = path.join(this.projectRoot, DEV_REQUIREMENTS_FILE);

    if (!fs.existsSync(requirementsFile)) {
      throw new Error(`缺少开发依赖文件：${requirementsFile}`);
    }

    if (!fs.existsSync(venvPython)) {
      this.#runBootstrapStep(
        baseCommand.file,
        [...(baseCommand.bootstrapArgs || []), "-m", "venv", venvDir],
        "首次启动，正在创建项目 Python 环境..."
      );
    }
    this.#runBootstrapStep(venvPython, ["-m", "pip", "install", "-r", requirementsFile], "正在安装 Python 依赖...");

    return this.#buildPythonCommand(venvPython, [], "repo .venv");
  }

  #devCommand() {
    const configuredPython = process.env.RELATION_GRAPH_DEV_PYTHON || process.env.RELATION_GRAPH_PYTHON;
    if (configuredPython) {
      return this.#resolveValidatedDevCommand([
        this.#buildPythonCommand(configuredPython, [], "configured Python")
      ]);
    }

    if (process.platform === "win32") {
      const candidateCommands = [];

      const repoVenvCandidates = [
        { path: path.join(this.projectRoot, ".venv", "Scripts", "python.exe"), label: "repo .venv" },
        { path: path.join(this.projectRoot, "venv", "Scripts", "python.exe"), label: "repo venv" },
        { path: path.join(this.projectRoot, ".build-tools", "backend-packager", "Scripts", "python.exe"), label: "packager venv" }
      ];
      for (const candidate of repoVenvCandidates) {
        if (fs.existsSync(candidate.path)) {
          candidateCommands.push(this.#buildPythonCommand(candidate.path, [], candidate.label));
        }
      }

      const activeEnvironmentCandidates = [
        { path: process.env.VIRTUAL_ENV ? path.join(process.env.VIRTUAL_ENV, "Scripts", "python.exe") : null, label: "active virtualenv" },
        { path: process.env.CONDA_PYTHON_EXE || null, label: "active conda python" },
        { path: process.env.CONDA_PREFIX ? path.join(process.env.CONDA_PREFIX, "python.exe") : null, label: "active conda prefix" }
      ].filter((candidate) => Boolean(candidate.path));
      for (const candidate of activeEnvironmentCandidates) {
        if (fs.existsSync(candidate.path)) {
          candidateCommands.push(this.#buildPythonCommand(candidate.path, [], candidate.label));
        }
      }

      const pyLauncher = path.join(process.env.SystemRoot || "C:\\Windows", "py.exe");
      if (fs.existsSync(pyLauncher)) {
        candidateCommands.push(this.#buildPythonCommand(pyLauncher, ["-3"], "py launcher"));
      }

      const userPython = path.join(process.env.LOCALAPPDATA || "", "Python", "bin", "python.exe");
      if (fs.existsSync(userPython)) {
        candidateCommands.push(this.#buildPythonCommand(userPython, [], "user Python"));
      }

      try {
        return this.#resolveValidatedDevCommand(candidateCommands);
      } catch (error) {
        const bootstrapBase = candidateCommands.find((candidate) => candidate.label === "py launcher") || candidateCommands[0];
        if (!bootstrapBase) {
          throw error;
        }
        const bootstrappedCommand = this.#bootstrapProjectVenv(bootstrapBase);
        return this.#resolveValidatedDevCommand([bootstrappedCommand]);
      }
    }

    const unixCandidates = [
      { path: path.join(this.projectRoot, ".venv", "bin", "python"), label: "repo .venv" },
      { path: path.join(this.projectRoot, "venv", "bin", "python"), label: "repo venv" },
      { path: path.join(this.projectRoot, ".build-tools", "backend-packager", "bin", "python"), label: "packager venv" },
      { path: process.env.VIRTUAL_ENV ? path.join(process.env.VIRTUAL_ENV, "bin", "python") : null, label: "active virtualenv" }
    ].filter((candidate) => Boolean(candidate.path));
    const candidateCommands = [];
    for (const candidate of unixCandidates) {
      if (fs.existsSync(candidate.path)) {
        candidateCommands.push(this.#buildPythonCommand(candidate.path, [], candidate.label));
      }
    }

    try {
      return this.#resolveValidatedDevCommand(candidateCommands);
    } catch (error) {
      const bootstrapBase = candidateCommands[0];
      if (!bootstrapBase) {
        throw error;
      }
      const bootstrappedCommand = this.#bootstrapProjectVenv(bootstrapBase);
      return this.#resolveValidatedDevCommand([bootstrappedCommand]);
    }
  }
}

module.exports = {
  PythonWorkerClient
};
