# 源数据目录约定

平台默认从项目根目录读取比赛源数据：

```text
yinyebei-factor-platform/
├── DailyData20240102open.bin
├── Minute20200102.mat
├── Minute20200103.mat
└── ...
```

`model/data_pipeline.py` 中的 `DATA_DIR` 是仓库根目录。若数据放在其他目录，可在初始化
`DataPipeline(data_dir=...)` 时传入路径，或把数据软链接/复制到根目录。

## 必需数据

- `DailyData20240102open.bin`：日频行情、标签、股票列表、交易日历。
- `MinuteYYYYMMDD.mat`：逐日分钟数据，包含 `MINUTE_OPEN/HIGH/LOW/CLOSE/VOLUME/AMOUNT/NUMBER`。

## 本仓库状态

- `DailyData20240102open.bin` 已按 90MB 分卷放在 `large_artifacts/split/`。
- 全量分钟数据体积约 12GB，记录在 `large_artifacts/local_only_too_large.json`。
- 若没有分钟数据，仍可校验最终提交因子、读取数据库和运行部分日频表达式；涉及日内微观结构的重算需要分钟数据。
