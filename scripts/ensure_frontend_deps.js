const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const root = path.resolve(__dirname, "..");
const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm";
const requiredBins = ["concurrently", "wait-on", "vite", "vitest", "electron"];

function quoteArg(value) {
  return /[\s"]/u.test(value) ? `"${String(value).replaceAll('"', '\\"')}"` : String(value);
}

function hasFrontendDeps() {
  return requiredBins.every((binName) => {
    const suffix = process.platform === "win32" ? ".cmd" : "";
    return fs.existsSync(path.join(root, "node_modules", ".bin", `${binName}${suffix}`));
  });
}

function installFrontendDeps() {
  const hasLockfile = fs.existsSync(path.join(root, "package-lock.json"));
  const args = [hasLockfile ? "ci" : "install"];
  console.log(`[RelationGraph] Frontend dependencies missing, running ${npmCommand} ${args.join(" ")}...`);
  const result = process.platform === "win32"
    ? spawnSync(process.env.ComSpec || "cmd.exe", ["/d", "/s", "/c", [npmCommand, ...args].map(quoteArg).join(" ")], {
        cwd: root,
        stdio: "inherit",
        windowsHide: true,
        env: process.env
      })
    : spawnSync(npmCommand, args, {
        cwd: root,
        stdio: "inherit",
        windowsHide: true,
        env: process.env
      });
  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`${npmCommand} ${args.join(" ")} failed with exit code ${result.status}`);
  }
}

if (!hasFrontendDeps()) {
  installFrontendDeps();
}
