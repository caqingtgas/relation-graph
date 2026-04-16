# RelationGraph / 关系织图

基于 `Vue 3 + Electron + Python` 的 Windows 本地图谱工具。

上传 `pdf`、`txt`、`md` 文档后，RelationGraph 会抽取结构化关系、聚合图结构，并生成可交互图谱页面与导出文件。桌面端负责界面、文件选择和运行控制，Python 后端负责图谱生成、本地模型管理与产物输出。

当前仓库版本：`v1.0.4`

## 当前技术结构

- 桌面壳：Electron
- 前端界面：Vue 3 + Vite + TypeScript
- 图谱后端：FastAPI 内部服务
- 核心能力：Python pipeline、本地 Ollama 管理、Ark 云端调用

## 快速开发

### 1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 2. 安装前端依赖

```bash
npm install
```

### 3. 启动桌面开发版

```bash
npm run dev
```

Windows 下也可以直接使用：

```bat
启动桌面开发版.bat
```

开发模式下：

- Vite 提供 renderer 页面
- Electron 启动桌面窗口
- Electron 主进程会自动启动本机 Python 后端
- Windows 下默认优先使用仓库内 `.venv`，否则回退到 `py -3`，不再依赖 PATH 中的 `python`

## 打包桌面版

### 1. 安装桌面打包所需 Python 依赖

```bash
pip install -r requirements-desktop.txt
```

如需显式指定打包解释器，可设置：

```bash
set RELATION_GRAPH_PACKAGER_PYTHON=C:\Path\To\python.exe
```

桌面后端打包默认只接受标准 CPython `3.9` 到 `3.13`，不会再静默回退到当前终端里的 Conda Python 或任意其它版本。

如果你只是临时验证，确实要放行其它版本，也必须显式设置：

```bash
set RELATION_GRAPH_ALLOW_UNSUPPORTED_PYTHON=1
```

### 2. 生成绿色版目录

```bash
npm run dist:dir
```

产物输出目录：

```text
desktop-dist/electron/win-unpacked/
```

这是首发桌面版的绿色目录，可直接解压使用，不依赖用户额外安装 Python 或 Node。

桌面后端打包会优先选择独立 CPython 解释器，不再默认继承当前调用终端的 Conda Python。

## 支持的生成路径

| 路径 | 说明 | 适用情况 |
| --- | --- | --- |
| 本地 Ollama | 本机优先，不依赖云端 API | 你已经准备好 Ollama 嵌入版本体和模型目录 |
| 火山方舟 Ark | 通过运行时填写 API Key 调用云端 | 想先快速使用，或本地模型未就绪 |

默认云端配置：

- Model ID: `doubao-seed-1-8-251228`
- Base URL: `https://ark.cn-beijing.volces.com/api/v3`
- Endpoint Path: `/chat/completions`

API Key 运行时通过桌面界面输入。

## 输出内容

每次生成成功后，程序会在运行目录中输出：

- 图谱页面 `graph.html`
- 独立可打开图谱 `graph_standalone.html`
- 文本分块 CSV
- 基础关系 CSV
- 聚合关系 CSV
- 元数据 JSON

图谱页面现在使用相对资源路径，可直接通过本地文件打开，不依赖浏览器静态服务。

## 本地路线说明

仓库不提交 Ollama 嵌入版本体，也不提交模型文件。

如果你要使用本地路线，需要自行准备：

- `ollama-windows-amd64.zip` <https://github.com/ollama/ollama/releases/tag/v0.20.5>
- 本地模型目录

嵌入式 Ollama 默认位置：

```text
relation_graph/embedded_runtime/ollama/ollama.exe
```

进入桌面版后，默认就在“本地”模式。首次使用时按下面顺序操作：

1. 点击 `下载模型并配置目录`
2. 选择模型下载目录
3. 程序会启动嵌入式 Ollama，并打开 PowerShell 下载窗口
4. 自动下载：
   - `qwen3.5:9b`
   - `qwen3.5:4b`
5. 下载完成后回到桌面版，即可直接生成图谱

如果你已经有模型：

1. 点击 `已有模型并配置目录`
2. 选择现有模型目录
3. 若状态显示可启动，可再点击 `启动本地引擎`

## 仓库清理原则

仓库长期只保留：

- 核心源码
- 测试代码
- 最小公开文档
- 图谱运行时主静态资源

以下内容不会进入 Git：

- `runtime_state/`
- `data_output/`
- `relation_graph/embedded_runtime/`
- `desktop-dist/`
- `dist/`
- `node_modules/`
- `.build-tools/`
- 缓存、日志、临时目录、模型文件、运行结果

## 测试

Python:

```bash
pytest -q
```

前端:

```bash
npm test
```

构建 renderer:

```bash
npm run build
```

## 致谢

本项目受到 [`rahulnyk/knowledge_graph`](https://github.com/rahulnyk/knowledge_graph) 的启发。
