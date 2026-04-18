# 验证指南

这是一套最小但完整的本地验证顺序。

## 日常验证

```bash
npm.cmd run verify
```

这条命令会依次执行：

- 前端依赖自举检查
- Python tests
- Vitest
- renderer build
- Electron / Node 关键脚本语法检查

## 分项命令

如果只想单独排查某一层，可以按下面顺序执行。

### Python

```bash
pip install -r requirements.txt
python -m pytest -q
```

### 前端

```bash
npm.cmd run setup:frontend
npm.cmd test
npm.cmd run build:renderer
```

### 脚本自检

```bash
python -m py_compile scripts/build_backend.py
python -m compileall -q relation_graph scripts tests
node --check electron/main.js
node --check electron/preload.js
node --check electron/python-worker-client.js
node --check scripts/run_build_backend.js
```

## 发布级检查

```bash
npm.cmd run verify:dist
```

这条命令会在打包成功后追加一次桌面启动 smoke，并在系统临时目录输出窗口截图，用来确认绿色目录确实能拉起主窗口。

## 判定标准

- Python tests 通过
- Vitest 通过
- renderer build 通过
- 脚本语法检查通过
- worker / dist 构建只在需要发布时跑
- 发布级验证需要看到打包后的桌面窗口可正常拉起
