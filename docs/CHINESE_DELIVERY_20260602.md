# YYB 中文最终交付索引

日期：2026-06-02

## 主交付物

- 中文论文 PDF：`D:\yyb\paper\afternoon_final_submission_zh.pdf`
- 中文论文 LaTeX：`D:\yyb\paper\afternoon_final_submission_zh.tex`
- 逐因子经济含义说明：`D:\yyb\paper\afternoon_final_factor_economics_zh.md`
- 逐因子机器可读 JSON：`D:\yyb\paper\afternoon_final_factor_economics_zh.json`
- 最终因子中文 TSV：`D:\yyb\paper\afternoon_final_factors_zh.tsv`
- 中文交付独立审计：`D:\yyb\paper\afternoon_chinese_delivery_audit.json`

## 论文范围

中文论文共 15 页，已扩展为完整项目报告。正文包含：

1. 比赛任务、预测对象和最终硬约束；
2. 本地 A 股数据口径；
3. Flask、SQLite、NumPy 回测平台；
4. 写缓存、读缓存、内联计算组成的递归套娃链路；
5. 市值中性化、缓存写入、读取越界、非浮点字段和内存治理修复；
6. 原子因子、组合方式、中性化、跨风格组合和套娃实验路线；
7. 950 条扩展实验、11 个创新阶段、贪心相关性阈值对照；
8. 最终 10 个因子的指标、明确经济含义、子因子含义和风险；
9. 顺序分段审计、顶会标准差距、未触碰留出集计划；
10. 从头到尾的项目完成清单和复现文件。

## 中文审计结果

- 审计状态：通过
- 最终因子数：10
- 最低实测样本外 Sharpe：10.722
- 最高实测样本外 Sharpe：16.247
- 最大两两日度 PnL 绝对相关性：0.4980399457
- PDF 页数：15
- 本地 Flask 登录页：HTTP 200

## 在线审查

- 本地：`http://127.0.0.1:5000/login`
- ngrok：`https://remark-glance-tweet.ngrok-free.dev/login`
- Cloudflare 备用：`https://tries-decision-avenue-facing.trycloudflare.com/login`

## 复现脚本

- 中文生成器：`D:\yyb\backtest_platform\generate_afternoon_submission_zh.py`
- 中文审计器：`D:\yyb\backtest_platform\audit_afternoon_submission_zh.py`

## 边界说明

英文冻结证据包未被覆盖。中文稿是独立补充交付。

2023 年研究阶段样本外窗口已经被自适应检查，因此当前高 Sharpe 是内部研究证据，不是未知未来收益保证。未触碰留出集、交易成本、容量、涨跌停、T+1、多重检验和滚动相关性仍需按预注册协议继续验证。

本次流程未提交任何外部 Alpha。
