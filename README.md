# RelationGraph / 关系织图

本机优先、支持本地与 Ark 双路径的文档关系图谱工具。

上传 `pdf`、`txt`、`md` 文档后，RelationGraph 会抽取结构化关系、聚合图结构，并生成可交互图谱页面与导出文件。

## 它适合什么场景

- 从文档里快速梳理实体、概念、模块和依赖关系
- 把非结构化说明文档转成可浏览的关系网络
- 在本机优先的前提下，按需切换本地模型或 Ark 云端模型

## 核心特点

- 图谱生成质量优先，不以简化牺牲结果质量
- 本地路线与云端路线并存
- 结构化输出优先，避免依赖脆弱的格式控制
- 项目目录保持干净，运行产物不进入仓库
- 首次启动所需最小源码与主静态资源直接随仓库保留

## 快速启动

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动项目

```bash
python -m knowledge_graph.run_web
```

Windows 下也可以直接使用：

```bat
启动图谱网页.bat
```

默认地址：

`http://127.0.0.1:8000`

## 支持的生成路径

| 路径 | 说明 | 适用情况 |
| --- | --- | --- |
| 本地 Ollama | 本机优先，不依赖云端 API | 你已经准备好本地运行时和模型目录 |
| 火山方舟 Ark | 通过运行时填写 API Key 调用云端 | 想先快速使用，或本地模型未就绪 |

默认云端配置：

- Model ID: `doubao-seed-1-8-251228`
- Base URL: `https://ark.cn-beijing.volces.com/api/v3`
- Endpoint Path: `/chat/completions`

API Key 不写入仓库，运行时通过界面输入。

## 输出内容

生成成功后，项目会输出图谱页面和结构化导出文件，主要包括：

- 交互式图谱页面
- 独立可打开的图谱 HTML
- 原始关系 CSV
- 聚合关系 CSV
- 元数据 JSON

## 本地路线说明

仓库默认不提交 `embedded_runtime` 等本地运行时二进制，也不提交模型文件。

如果你要使用本地路线，按下面的顺序准备。

### 1. 下载 Ollama 的 Windows 独立包

优先看 Ollama 官方 Windows 文档：

- https://docs.ollama.com/windows

如果你需要用于嵌入式集成的独立包，官方文档指向最新版 Releases：

- https://github.com/ollama/ollama/releases

按 Ollama 官方 Windows 文档，独立 CLI 的基础包是：

- `ollama-windows-amd64.zip`

如果你的硬件需要额外包，按官方 Windows 文档和 Releases 页面选择并解压到同一目录。

### 2. 放到项目期望的位置

本项目要求 `ollama.exe` 位于：

```text
knowledge_graph/embedded_runtime/ollama/ollama.exe
```

因此做法不是“只复制一个 exe”，而是把 Ollama Windows 独立包完整解压到：

```text
knowledge_graph/embedded_runtime/ollama/
```

解压完成后，至少应看到类似结构：

```text
knowledge_graph/
  embedded_runtime/
    ollama/
      ollama.exe
      lib/
```

### 3. 启动项目后下载模型

启动项目后：

1. 保持左侧在“本地”模式
2. 点击“下载模型并配置目录”
3. 在弹出的系统目录选择窗口里，选择一个专门存放模型的目录
   - 例如：`E:\\models`
4. 确认后，程序会自动：
   - 记住这个模型目录
   - 启动嵌入式 Ollama
   - 打开一个 PowerShell 下载窗口
   - 依次下载 `qwen3.5:9b` 和 `qwen3.5:4b`

下载窗口关闭后，页面会自动轮询刷新本地状态。

### 4. 如果你已经有模型目录

如果你之前已经用 Ollama 下载过模型，不需要重新下载：

1. 启动项目
2. 保持左侧在“本地”模式
3. 点击“已有模型并配置目录”
4. 选择已经包含 Ollama 模型清单的目录

当前项目只会识别这两个白名单模型：

- `qwen3.5:9b`
- `qwen3.5:4b`

### 5. 本地引擎的启动方式

如果目录已经配置好，但状态显示“运行时当前未启动”，可以直接点击：

- “启动本地引擎”

项目会在本机启动嵌入式 Ollama，并把模型目录通过 `OLLAMA_MODELS` 指向你刚才选择的目录。

如果你暂时不使用本地路线，也可以直接填写火山方舟 API Key 走云端生成。

## 静态资源说明

图谱运行时主资源保存在：

- `knowledge_graph/graph_assets/vis-network.min.js`
- `knowledge_graph/graph_assets/vis-network.min.css`

首次启动时如果 `knowledge_graph/static/vendor/` 不存在，程序会自动从 `graph_assets` 复制补齐。

## 已知限制

- 当前首发定位为 Windows 本机工具
- 本地路线依赖你自行准备的本地运行时与模型目录
- 云端路线需要运行时填写 API Key
- 当前不包含 GitHub Actions、自动发布流程和额外工程化包装

## 仓库清理原则

仓库长期只保留：

- 核心源码
- 测试代码
- 最小公开文档
- 首次启动必需的主静态资源

以下内容不会进入 GitHub：

- `runtime_state/`
- `knowledge_graph/data_output/`
- `knowledge_graph/embedded_runtime/`
- `knowledge_graph/static/vendor/`
- 缓存、日志、临时目录、模型文件、运行结果
- 本地便签、分析稿、验证产物

## 测试

```bash
pytest -q
```

## 致谢

本项目受到 [`rahulnyk/knowledge_graph`](https://github.com/rahulnyk/knowledge_graph) 的启发。
