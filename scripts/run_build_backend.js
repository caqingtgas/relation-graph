const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const root = path.resolve(__dirname, "..");
const targetScript = path.join(root, "scripts", "build_backend.py");

function isWindows() {
  return process.platform === "win32";
}

function buildCandidates() {
  const candidates = [];
  const pushCandidate = (file, args = []) => {
    if (!file) {
      return;
    }
    const normalized = file.trim();
    if (!normalized) {
      return;
    }
    if (path.isAbsolute(normalized) && !fs.existsSync(normalized)) {
      return;
    }
    candidates.push({ file: normalized, args });
  };

  pushCandidate(process.env.RELATION_GRAPH_PACKAGER_PYTHON);
  pushCandidate(process.env.RELATION_GRAPH_PYTHON);

  if (isWindows()) {
    pushCandidate(path.join(root, ".venv", "Scripts", "python.exe"));
    pushCandidate(path.join(root, "venv", "Scripts", "python.exe"));
    pushCandidate(path.join(root, ".build-tools", "backend-packager", "Scripts", "python.exe"));

    const pyLauncher = path.join(process.env.SystemRoot || "C:\\Windows", "py.exe");
    if (fs.existsSync(pyLauncher)) {
      candidates.push({ file: pyLauncher, args: ["-3"] });
    }

    const userPython = path.join(process.env.LOCALAPPDATA || "", "Python", "bin", "python.exe");
    pushCandidate(userPython);
    candidates.push({ file: "python", args: [] });
  } else {
    pushCandidate(path.join(root, ".venv", "bin", "python"));
    pushCandidate(path.join(root, "venv", "bin", "python"));
    pushCandidate(path.join(root, ".build-tools", "backend-packager", "bin", "python"));
    candidates.push({ file: "python3", args: [] });
    candidates.push({ file: "python", args: [] });
  }

  return candidates;
}

function runWithCandidate(candidate) {
  const result = spawnSync(candidate.file, [...candidate.args, targetScript], {
    cwd: root,
    stdio: "inherit",
    env: process.env,
    windowsHide: true,
  });

  if (result.error) {
    return { ok: false, detail: result.error.message };
  }

  if (typeof result.status === "number") {
    return { ok: result.status === 0, status: result.status, detail: `exit ${result.status}` };
  }

  return { ok: false, detail: "unknown failure" };
}

const candidates = buildCandidates();
const failures = [];

for (const candidate of candidates) {
  const outcome = runWithCandidate(candidate);
  if (outcome.ok) {
    process.exit(0);
  }
  failures.push(`${candidate.file} ${candidate.args.join(" ")}`.trim() + ` -> ${outcome.detail}`);
}

console.error("No usable Python launcher found for build_backend.py.");
if (failures.length > 0) {
  console.error(failures.join("\n"));
}
process.exit(1);
