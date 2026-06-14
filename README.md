# 银叶杯因子平台与最终提交包

本仓库是银叶杯初赛项目的公开交接仓库。它以桌面文件
`银叶杯_三个臭诸葛亮_初赛结果.zip` 的最终提交逻辑为准，保留最终提交四件套、
因子研究平台、回测数据库、真实实验日志、论文材料、运行脚本和新电脑恢复说明。

## 最终提交口径

- 最终提交因子：`ultimate_lgb`
- 提交形态：一个标准化因子矩阵，不是十个独立因子
- 覆盖区间：2020-01-02 至 2023-12-29
- 矩阵形状：970 个交易日 × 5515 只股票
- 研究划分：2020-2022 为 IS，2023 为完全样本外 OS/OOS
- 公开冻结提交包：`submission/银叶杯_三个臭诸葛亮_初赛结果.zip`
- 解压后的四个提交文件：`submission/official_initial_round_result/`

## 仓库结构

```text
backtest_platform/          Flask 平台、组合回测、LGB、实验脚本
model/                      数据管线、表达式解析、回测引擎、因子库
model/artifacts/            小于 100MB 的模型产物和结果表
submission/                 最终可提交 zip、官方四件套、平台源码 zip
runtime_state/              SQLite 数据库、真实实验 JSON/JSONL、运行日志
paper/                      论文、图表、LaTeX/PDF、审计输出
large_artifacts/            分卷上传的大文件和未上传超大文件清单
tools/                      恢复分卷、交接完整性验证脚本
docs/                       交接文档、复现说明、平台说明
```

## 新电脑最快接手

```powershell
git clone https://github.com/thoanghiemdung-del/yinyebei-factor-platform.git
cd yinyebei-factor-platform
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python tools\verify_handoff.py
python tools\restore_large_artifacts.py
```

启动平台：

```powershell
Copy-Item runtime_state\backtest_platform\backtest.db backtest_platform\backtest.db
cd backtest_platform
python app.py
```

如果要从主办方源数据重新计算，需要把 `DailyData20240102open.bin` 和
`MinuteYYYYMMDD.mat` 放到仓库根目录或按 `docs/SOURCE_DATA_LAYOUT.md` 设置数据目录。
`DailyData20240102open.bin` 已在 `large_artifacts/split/` 中分卷上传，可用
`python tools\restore_large_artifacts.py` 恢复；12GB 级分钟压缩包和 5GB 级全量缓存
因 GitHub 公开仓库体积限制记录在 `large_artifacts/local_only_too_large.json`。

## 重要说明

1. `submission/official_initial_round_result/银叶杯.py` 是比赛提交侧的冻结因子加载器，
   读取 `因子值.xlsx` 并返回 `ultimate_lgb` 矩阵。
2. 从源数据重算的研究逻辑在 `backtest_platform/` 与 `model/` 中：
   叶子因子生成、风格组合、LGB 训练、IS/OOS 评估、实验记录都在平台代码和数据库中。
3. 公开仓库没有上传账号 cookie、API key、ngrok token 等凭据。
4. 本仓库最后整理时间：2026-06-14 09:49:24。
