# 开发环境搭建

面向本地开发的最小步骤如下。

## 前置条件

- Windows
- Python 3.9 到 3.13 的标准 CPython
- Node.js 20+ 和 npm

## 安装

在仓库根目录执行：

```bash
npm.cmd run setup:frontend
pip install -r requirements.txt
```

如果要跑桌面打包相关脚本，再补装：

```bash
pip install -r requirements-desktop.txt
```

## 启动

```bash
npm.cmd run dev
```

Windows 下也可以双击：

```text
启动桌面开发版.bat
```

## 常用环境变量

- `RELATION_GRAPH_PACKAGER_PYTHON`: 显式指定桌面打包解释器
- `RELATION_GRAPH_ALLOW_UNSUPPORTED_PYTHON`: 临时放行不受支持的打包解释器版本
- 如果 PowerShell 拦截了 `npm.ps1`，直接改用 `npm.cmd`

## 目录提示

- 开发期生成物不要手工提交
- `dist/`、`desktop-dist/`、`node_modules/`、`.venv/` 都应保持在 Git 之外
- 日常自检优先使用 `npm.cmd run verify`
