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
| 本地 Ollama | 本机优先，不依赖云端 API | 你已经准备好 Ollama 嵌入版本体和模型目录 |
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

仓库不提交 Ollama 嵌入版本体，也不提交模型文件。

如果你要使用本地路线，需要自行准备：

- `ollama-windows-amd64.zip` <https://github.com/ollama/ollama/releases/tag/v0.20.5>
- 本地模型目录

### 1. 下载 Ollama 嵌入版

本项目依赖的是 Ollama 的 Windows standalone CLI 包。

官方入口：

- `ollama-windows-amd64.zip` <https://github.com/ollama/ollama/releases/tag/v0.20.5>

### 2. 解压到项目要求的位置

本项目代码固定要求 `ollama.exe` 位于：

`knowledge_graph/embedded_runtime/ollama/ollama.exe`

也就是说，你应该把官方 zip 的完整内容解压到这个目录。

推荐解压后的结构类似这样：

```text
relation-graph/
  knowledge_graph/
    embedded_runtime/
      ollama/
        ollama.exe
        lib/
        ...
```

### 3. 启动项目后如何下载模型

启动项目：

```bash
python -m knowledge_graph.run_web
```

进入页面后，默认就在“本地”模式。首次使用时按下面顺序操作：

1. 点击 `下载模型并配置目录`
2. 程序会弹出 Windows 目录选择窗口，标题是“选择模型下载目录”
3. 选择一个用于保存模型的目录，例如 `E:\models`
4. 确认后，程序会自动：
   - 把该目录保存为本地模型目录
   - 启动嵌入式 Ollama
   - 打开一个 PowerShell 窗口
   - 在你刚选的目录里依次下载：
     - `qwen3.5:9b`
     - `qwen3.5:4b`
5. 等下载终端完成后，页面状态会刷新
6. 当页面显示“本地模型已就绪”后，就可以直接用本地模式生成图谱

### 4. 如果你已经有本地模型

如果模型已经提前下载好了，不需要再点“下载模型并配置目录”，而是：

1. 点击 `已有模型并配置目录`
2. 在弹出的目录窗口里选择现有模型目录
3. 目录里需要能被 Ollama 识别到对应白名单模型

当前项目白名单只有两个模型：

- `qwen3.5:9b`
- `qwen3.5:4b`

### 5. 之后如何启动本地引擎

如果模型目录已经配置好，但本地引擎当前未启动，页面会出现 `启动本地引擎` 按钮。

点击后，项目会：

- 用仓库内的嵌入式 Ollama 启动本地服务
- 把模型目录绑定到你之前选择的目录
- 使用独立端口 `127.0.0.1:11435`

这意味着它不会依赖你系统里额外常驻的默认 Ollama 服务。

## 静态资源说明

图谱运行时主资源保存在：

- `knowledge_graph/graph_assets/vis-network.min.js`
- `knowledge_graph/graph_assets/vis-network.min.css`

首次启动时如果 `knowledge_graph/static/vendor/` 不存在，程序会自动从 `graph_assets` 复制补齐。

## 已知限制

- 当前定位为 Windows 本机工具
- 本地路线依赖你自行准备的Ollama 嵌入版本体与模型目录
- 云端路线需要运行时填写火山方舟 API Key
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
