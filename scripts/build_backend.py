from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BUILD_TOOLS_DIR = ROOT / ".build-tools"
PACKAGER_VENV = BUILD_TOOLS_DIR / "backend-packager"
PACKAGER_STAMP = PACKAGER_VENV / ".requirements.stamp"
DIST_ROOT = ROOT / "desktop-dist"
BACKEND_DIST = DIST_ROOT / "backend"
PYI_BUILD = DIST_ROOT / "pyinstaller-build"
PYI_SPEC = DIST_ROOT / "pyinstaller-spec"
BACKEND_NAME = "relation-graph-worker"
REQUIREMENT_FILES = (ROOT / "requirements.txt", ROOT / "requirements-desktop.txt")
INSTALL_REQUIREMENTS_FILE = ROOT / "requirements-desktop.txt"
DEFAULT_WINDOWS_PYTHON = Path(os.environ.get("LOCALAPPDATA", "")) / "Python" / "bin" / "python.exe"
DEFAULT_WINDOWS_LAUNCHER = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "py.exe"
WINDOWS_PREFERRED_PYTHON_VERSIONS = ("3.13", "3.12", "3.11", "3.10", "3.9")
SUPPORTED_PACKAGER_PYTHON_VERSIONS = frozenset(WINDOWS_PREFERRED_PYTHON_VERSIONS)
PYINSTALLER_EXCLUDES = (
    "IPython",
    "PIL",
    "Crypto",
    "brotli",
    "brotlicffi",
    "cryptography",
    "dotenv",
    "email_validator",
    "gunicorn",
    "h2",
    "httptools",
    "hypothesis",
    "lxml",
    "matplotlib",
    "mypy",
    "numpy",
    "outcome",
    "pandas",
    "pydot",
    "pygments",
    "pygraphviz",
    "pytest",
    "python_multipart",
    "rich",
    "scipy",
    "setuptools.command.bdist_wheel",
    "sniffio",
    "socksio",
    "sympy",
    "toml",
    "trio",
    "uvicorn.supervisors.watchfilesreload",
    "uvloop",
    "watchfiles",
    "websockets",
    "wsproto",
    "yaml",
    "zstandard",
)


def _venv_python_executable() -> Path:
    if sys.platform == "win32":
        return PACKAGER_VENV / "Scripts" / "python.exe"
    return PACKAGER_VENV / "bin" / "python"


def _run_python(executable: Path, args: list[str]) -> str:
    return subprocess.check_output(
        [str(executable), *args], cwd=str(ROOT), text=True, encoding="utf-8", stderr=subprocess.DEVNULL
    ).strip()


def _python_identity(executable: Path) -> str:
    return _run_python(
        executable,
        [
            "-c",
            "from pathlib import Path; import platform,sys; print(f\"{platform.python_implementation()}|{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}|{Path(sys.executable).resolve()}\")",
        ],
    )


def _python_version(executable: Path) -> str:
    return _run_python(
        executable,
        [
            "-c",
            "import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")",
        ],
    )


def _is_conda_interpreter(executable: Path) -> bool:
    resolved = executable.resolve()
    return any((candidate / "conda-meta").exists() for candidate in (resolved.parent, resolved.parent.parent))


def _py_launcher_runtimes() -> list[tuple[str, Path]]:
    if sys.platform != "win32" or not DEFAULT_WINDOWS_LAUNCHER.exists():
        return []
    try:
        output = _run_python(DEFAULT_WINDOWS_LAUNCHER, ["-0p"])
    except subprocess.CalledProcessError:
        return []

    runtimes: list[tuple[str, Path]] = []
    for line in output.splitlines():
        entry = line.strip()
        if not entry:
            continue
        match = re.match(r"^-V:([^\s]+)\s+\*?\s*(.+)$", entry)
        if not match:
            continue
        version, executable = match.groups()
        candidate = Path(executable.strip()).resolve()
        if candidate.exists():
            runtimes.append((version, candidate))
    return runtimes


def _is_supported_packager_python(executable: Path) -> bool:
    return _python_version(executable) in SUPPORTED_PACKAGER_PYTHON_VERSIONS


def _allow_unsupported_packager_python() -> bool:
    value = os.environ.get("RELATION_GRAPH_ALLOW_UNSUPPORTED_PYTHON", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _format_runtime_choices(runtimes: list[tuple[str, Path]]) -> str:
    if not runtimes:
        return "无"
    return ", ".join(f"{version} -> {executable}" for version, executable in runtimes)


def _resolve_base_python() -> Path:
    allow_unsupported = _allow_unsupported_packager_python()
    override = os.environ.get("RELATION_GRAPH_PACKAGER_PYTHON") or os.environ.get("RELATION_GRAPH_PYTHON")
    if override:
        executable = Path(override).expanduser().resolve()
        if not executable.exists():
            raise SystemExit(f"指定的 Python 不存在: {executable}")
        version = _python_version(executable)
        if not allow_unsupported and version not in SUPPORTED_PACKAGER_PYTHON_VERSIONS:
            raise SystemExit(
                "指定的打包解释器版本不受支持: "
                f"{version} ({executable})。请改用 CPython {', '.join(WINDOWS_PREFERRED_PYTHON_VERSIONS)}，"
                "或在确认兼容风险后设置 RELATION_GRAPH_ALLOW_UNSUPPORTED_PYTHON=1。"
            )
        return executable

    local_candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / "venv" / "Scripts" / "python.exe",
    ]
    for candidate in local_candidates:
        if candidate.exists() and not _is_conda_interpreter(candidate) and _is_supported_packager_python(candidate):
            return candidate.resolve()

    launcher_runtimes = _py_launcher_runtimes()
    for version in WINDOWS_PREFERRED_PYTHON_VERSIONS:
        for runtime_version, executable in launcher_runtimes:
            if runtime_version == version and not _is_conda_interpreter(executable):
                return executable

    if DEFAULT_WINDOWS_PYTHON.exists() and not _is_conda_interpreter(DEFAULT_WINDOWS_PYTHON):
        if _is_supported_packager_python(DEFAULT_WINDOWS_PYTHON):
            return DEFAULT_WINDOWS_PYTHON.resolve()

    if allow_unsupported:
        for candidate in local_candidates:
            if candidate.exists() and not _is_conda_interpreter(candidate):
                return candidate.resolve()

        if DEFAULT_WINDOWS_PYTHON.exists() and not _is_conda_interpreter(DEFAULT_WINDOWS_PYTHON):
            return DEFAULT_WINDOWS_PYTHON.resolve()

        for _, executable in launcher_runtimes:
            if not _is_conda_interpreter(executable):
                return executable

        current_python = Path(sys.executable).resolve()
        if current_python.exists() and not _is_conda_interpreter(current_python):
            return current_python

        raise SystemExit(
            "已显式允许不受支持的 Python，但仍未找到可用于桌面打包的独立 CPython。"
        )

    unsupported_runtimes = [
        (version, executable)
        for version, executable in launcher_runtimes
        if not _is_conda_interpreter(executable)
    ]
    current_python = Path(sys.executable).resolve()
    current_python_note = ""
    if current_python.exists():
        current_version = _python_version(current_python)
        current_python_note = f"当前解释器: {current_version} -> {current_python}"

    raise SystemExit(
        "未找到受支持的桌面打包解释器。"
        f" 需要标准 CPython {', '.join(WINDOWS_PREFERRED_PYTHON_VERSIONS)}。"
        f" 已发现的非 Conda 解释器: {_format_runtime_choices(unsupported_runtimes)}。"
        f" {current_python_note}"
        " 如需临时放行其它版本，请设置 RELATION_GRAPH_ALLOW_UNSUPPORTED_PYTHON=1，"
        "并建议同时显式设置 RELATION_GRAPH_PACKAGER_PYTHON。"
    )


def _requirements_fingerprint(base_python: Path) -> str:
    digest = hashlib.sha256()
    digest.update(b"backend-packager-v2\n")
    digest.update(_python_identity(base_python).encode("utf-8"))
    digest.update(b"\n")
    for requirement_file in REQUIREMENT_FILES:
        digest.update(requirement_file.name.encode("utf-8"))
        digest.update(b"\n")
        digest.update(requirement_file.read_bytes())
        digest.update(b"\n")
    return digest.hexdigest()


def _ensure_packager_environment() -> Path:
    BUILD_TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    base_python = _resolve_base_python()
    python_executable = _venv_python_executable()
    expected_fingerprint = _requirements_fingerprint(base_python)
    installed_fingerprint = PACKAGER_STAMP.read_text(encoding="utf-8").strip() if PACKAGER_STAMP.exists() else ""
    if not python_executable.exists() or installed_fingerprint != expected_fingerprint:
        if PACKAGER_VENV.exists():
            shutil.rmtree(PACKAGER_VENV)
        subprocess.run([str(base_python), "-m", "venv", str(PACKAGER_VENV)], cwd=str(ROOT), check=True)
        subprocess.run([str(python_executable), "-m", "pip", "install", "--upgrade", "pip"], cwd=str(ROOT), check=True)
        subprocess.run(
            [str(python_executable), "-m", "pip", "install", "-r", str(INSTALL_REQUIREMENTS_FILE)],
            cwd=str(ROOT),
            check=True,
        )
        PACKAGER_STAMP.write_text(expected_fingerprint, encoding="utf-8")
    return python_executable


def main() -> int:
    target_dir = BACKEND_DIST / BACKEND_NAME
    if target_dir.exists():
        shutil.rmtree(target_dir)

    DIST_ROOT.mkdir(parents=True, exist_ok=True)
    packager_python = _ensure_packager_environment()
    command = [
        str(packager_python),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        BACKEND_NAME,
        "--distpath",
        str(BACKEND_DIST),
        "--workpath",
        str(PYI_BUILD),
        "--specpath",
        str(PYI_SPEC),
        "--paths",
        str(ROOT),
        "--add-data",
        f"{ROOT / 'relation_graph' / 'graph_assets'};relation_graph/graph_assets",
        str(ROOT / "relation_graph" / "run_desktop_worker.py"),
    ]
    for module_name in PYINSTALLER_EXCLUDES:
        command.extend(["--exclude-module", module_name])

    embedded_runtime_dir = ROOT / "relation_graph" / "embedded_runtime"
    if embedded_runtime_dir.exists():
        command.extend(["--add-data", f"{embedded_runtime_dir};relation_graph/embedded_runtime"])

    subprocess.run(command, cwd=str(ROOT), check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
