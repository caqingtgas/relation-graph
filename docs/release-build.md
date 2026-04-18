# 发布与打包

本仓库的交付目标是 Windows 桌面目录包。

## 主要命令

```bash
npm.cmd run build:renderer
npm.cmd run build:worker
npm.cmd run dist:dir
```

## 产物位置

- renderer 构建结果：`dist/`
- worker 构建结果：`desktop-dist/backend/`
- Electron 打包目录：`desktop-dist/electron/win-unpacked/`

## 打包前检查

- 先确认 Python 依赖已安装
- 先确认 `npm.cmd install` 成功
- 需要桌面打包时，确认 `requirements-desktop.txt` 可用

## 说明

- `npm.cmd run build:worker` 会走 `scripts/run_build_backend.js`
- `scripts/build_backend.py` 会自动选择可用的打包 Python
- 如果环境里有多个 Python，优先显式设置 `RELATION_GRAPH_PACKAGER_PYTHON`

## 发布原则

- 只提交源码、测试和必要文档
- 不提交运行时目录、模型文件和构建产物
- 发布前先跑 [验证指南](validation.md)
