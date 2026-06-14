# 大文件与分卷恢复

GitHub 普通仓库不允许单个文件超过 100MB。本目录将中等大文件按 90MB 分卷保存。

恢复命令：

```powershell
python tools\restore_large_artifacts.py
```

恢复后文件位于 `restored_large_artifacts/`，脚本会校验 SHA256。

`local_only_too_large.json` 记录未直接上传的超大本地目录/文件。它们包括 12GB 级分钟数据、
5GB 级全量因子缓存和 5.9GB 级平台矩阵缓存；普通公开 Git 仓库不适合作为这些文件的载体。
