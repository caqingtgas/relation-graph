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

如果你要使用本地路线，需要自行准备：

- 本地嵌入式 Ollama 运行时
- 本地模型目录

如果不使用本地路线，可以直接填写火山方舟 API Key 走云端生成。

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
