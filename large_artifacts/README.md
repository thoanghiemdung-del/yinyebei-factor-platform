# 大文件与分卷恢复

GitHub 普通仓库不允许单个文件超过 100MB。本目录将中等大文件按 90MB 分卷保存。

恢复命令：

```powershell
python tools\restore_large_artifacts.py
```

恢复后文件位于 `restored_large_artifacts/`，脚本会校验 SHA256。

`full_nonminute/` 保存除分钟数据外的超大项目状态：`all_factors.pkl`、平台 cache、`submission_rebuild/`。
`local_only_too_large.json` 只记录用户明确排除的 12GB 级分钟数据。
