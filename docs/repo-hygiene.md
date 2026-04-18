# 仓库卫生规则

这个仓库已经完成产品化，后续维护只保留能长期复用的内容。

## 保留

- 源码
- 测试
- 必要文档
- 少量静态资源

## 不提交

- `dist/`
- `desktop-dist/`
- `node_modules/`
- `.venv/`
- `runtime_state/`
- `data_output/`
- `embedded_runtime/`
- `relation_graph/embedded_runtime/`
- `models/`
- 缓存、日志、临时文件

## 维护规则

- 新增文件先判断是不是生成物
- 先补文档和测试，再考虑改实现
- 不要为了“更完整”去加兼容分支或废弃兜底
- 变更保持增量，避免把 finished repo 改成大重构现场
