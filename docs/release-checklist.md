# 发布前检查清单

每次准备交付 Windows 绿色目录前，至少过一遍下面这份清单。

## 代码与仓库

- 工作树里没有运行产物、模型文件、缓存目录和临时日志
- README、开发说明、验证命令与实际脚本一致
- `.gitignore` 仍覆盖构建与运行噪音

## 验证

- `npm.cmd run verify`
- 如本次涉及打包链路，再跑 `npm.cmd run verify:dist`
- 关键改动至少做一轮真实桌面链路自测
- `verify:dist` 产生的桌面 smoke 截图要能看见主窗口而不是空白壳

## 本地路线

- `embedded_runtime/ollama/ollama.exe` 的外置约束说明仍准确
- 未配置目录、已配置未启动、已启动三种状态提示都清晰
- 手动启动终端与模型目录说明没有漂移

## 云端路线

- Ark 默认模型、Base URL、Endpoint Path 文案仍准确
- 未填 API Key 的错误提示清晰
- 填 Key 后的生成路径没有被最近改动破坏

## 产物

- `desktop-dist/electron/win-unpacked/` 可生成
- 结果目录、图谱预览、导出独立 HTML、打开产物路径都正常
