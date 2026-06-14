# 完整交接与复现说明

## 1. 任务基准

本仓库以后以桌面原始包 `银叶杯_三个臭诸葛亮_初赛结果.zip` 为准。该包包含：

- `银叶杯.py`
- `回测报告.docx`
- `因子逻辑说明文档.pdf`
- `因子值.xlsx`

最终因子是单一 `ultimate_lgb`，不是十个标准化因子。`因子值.xlsx` 是 970×5515 的冻结提交矩阵，
`银叶杯.py` 是比赛提交入口，负责加载并校验矩阵形状、日期和股票轴。

## 2. 项目从头到尾做了什么

1. 搭建 A 股因子研究平台：`model/data_pipeline.py` 读取日频和分钟数据，
   `model/backtest_framework.py` 统一计算 IC、Top10% 超额收益、Sharpe、最大回撤、正收益日占比等指标。
2. 搭建 Flask 交互平台：`backtest_platform/app.py` 提供表达式回测、因子历史、相关性检查、
   组合因子、LightGBM 组合和报告生成接口。
3. 构建叶子因子：覆盖流动性/换手、价格形态、多周期动量、容量约束、成交活跃度、日内微观结构等风格。
4. 构建风格组合：在 2020-2022 IS 内比较等权、ICIR、Sharpe/稳定性等加权方式。
5. 构建终极因子：将风格因子输入 LightGBM，使用 2020-2022 训练、5 个交易日 purge，
   只在最终阶段评估 2023 OOS。
6. 冻结提交：最终提交一个标准化 `ultimate_lgb` 因子矩阵和说明文档。

## 3. IS/OOS 口径

- IS：2020-01-02 至 2022-12-30
- OOS：2023-01-03 至 2023-12-29
- 2023 OOS 不参与终极因子确定前的筛选和调参。

## 4. 新电脑恢复步骤

```powershell
git clone https://github.com/thoanghiemdung-del/yinyebei-factor-platform.git
cd yinyebei-factor-platform
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python tools\verify_handoff.py
python tools\restore_large_artifacts.py
Copy-Item runtime_state\backtest_platform\backtest.db backtest_platform\backtest.db
python backtest_platform\app.py
```

## 5. 大文件恢复

`large_artifacts/split/` 中的文件是按 90MB 分卷上传的，运行
`python tools/restore_large_artifacts.py` 后会恢复到 `restored_large_artifacts/`。

未直接上传的超大文件记录在 `large_artifacts/local_only_too_large.json`，主要是：

- 12GB 级 `股票分钟数据.zip`
- 5GB 级 `模型/all_factors.pkl`
- 5.9GB 级 `backtest_platform/cache/`
- 4.9GB 级 `submission_rebuild/`

它们不进普通 GitHub 仓库是因为公开仓库单文件/总体积限制。接手者可以用主办方原始数据和本仓库代码重新生成。

## 6. 自查命令

```powershell
python tools\verify_handoff.py
git status --short
git log --oneline -5
```

`verify_handoff.py` 会检查官方 zip 四件套、最终因子矩阵形状、日期范围、SQLite 回测历史和分卷清单。
