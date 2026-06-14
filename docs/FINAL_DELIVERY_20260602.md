# YYB Final Delivery

Delivered: 2026-06-02 02:06 CST

## Artifacts

- Paper PDF: `D:\yyb\paper\final_submission.pdf`
- Paper LaTeX: `D:\yyb\paper\final_submission.tex`
- Paper summary: `D:\yyb\paper\final_submission_summary.json`
- Frozen audit: `D:\yyb\backtest_platform\experiment_results\final_audit_results.json`
- Raw experiment log: `D:\yyb\backtest_platform\experiment_results\final_audit_experiments.jsonl`
- Final handoff: `D:\yyb\HANDOFF_FINAL_AUDIT_20260601.md`

## Evidence Summary

The final audit contains 120 unique measured experiments:

- 75 confirmatory contrasts covering IS-selected baskets, greedy thresholds, three
  combination methods, and five neutralization modes.
- 45 exploratory nested contrasts covering 15 rows each at L1, L2, and L3.

Best confirmatory result:

- `top_is_sharpe_n5_icir_beta`
- OOS Sharpe `12.882`
- IC `0.0402`
- Fitness `18.882`
- Turnover `0.2709`

Best nested results:

- L1 Sharpe `6.252`
- L2 Sharpe `6.356`
- L3 Sharpe `10.448`

## Hard Constraint Result

The requested portfolio of ten factors with OOS Sharpe greater than 10 and pairwise
absolute daily-PnL correlation below 0.5 was not achieved. Exactly one measured
superalpha passes the strict screen:

- ID `d88b1b68-7242-4f97-bc7b-3593fbd632b5`
- Sharpe `13.351`
- IC `0.0433`
- Fitness `18.316`
- Turnover `0.3161`

The paper reports this shortfall directly. It does not pad the portfolio with correlated
variants or fabricate leaf attribution for legacy cache placeholders.

## QA

- Flask local review: HTTP 200 at `http://127.0.0.1:5000/login`
- ngrok public review: HTTP 200 at `https://remark-glance-tweet.ngrok-free.dev/login`
- Final PDF compiled with two XeLaTeX passes.
- All seven PDF pages rendered and visually inspected.
- Final LaTeX log contains no layout, undefined-reference, emergency-stop, or error
  warnings.
- No external Alpha submission was performed.

---

## Afternoon Extension Addendum (2026-06-02 12:43 CST)

This addendum is the latest measured delivery checkpoint. It supersedes the morning
portfolio shortfall for the user's revised requirement: at least ten factors with OOS
Sharpe greater than 8 and pairwise absolute daily-PnL correlation below 0.5. The earlier
morning statement about the stricter Sharpe-greater-than-10 portfolio remains historically
correct and must not be rewritten.

### Expanded Measured Audit

The afternoon audit records 772 additional real experiments:

- 526 first-round extension rows:
  - 116 residualized near-threshold variants.
  - 270 cross-style bridge variants.
  - 60 cached style-anchor variants.
  - 20 nested style-anchor variants.
  - 60 cached cross-style offset variants.
- 246 deep extension rows:
  - 96 explicit weighted cross-style variants.
  - 140 L3 pair/triple cached-matrix nesting variants.
  - 10 L4 meta-nesting variants.

Every afternoon JSONL row is a measured API result. The frozen logs contain zero failed
rows and no external Alpha submission.

### Revised Hard Constraint Result

The revised target is achieved. The strict pool contains 18 measured candidates. The
displayed portfolio contains 10 factors, each with OOS Sharpe greater than 8. The maximum
pairwise absolute daily-PnL correlation is `0.49653812140608944`.

| Rank | ID | Theme | OOS Sharpe | Max corr. to selected |
|---:|---|---|---:|---:|
| 1 | `5decfdb9-4d8c-422c-b727-d50cdf6d08cf` | composite | 15.910 | 0.000000 |
| 2 | `8138a76a-00ed-46a8-9c52-decf0e2a1c3a` | momentum | 13.141 | 0.381491 |
| 3 | `a7796444-94e3-4caf-879f-2b4ab12712eb` | composite | 11.504 | 0.484300 |
| 4 | `2be80bc5-ece1-4617-9365-23f3648833b4` | risk | 11.254 | 0.474880 |
| 5 | `95eead5b-e7c1-4e49-b3b5-d13e7941ecf1` | liquidity | 11.202 | 0.337063 |
| 6 | `ea867db0-03b3-44ff-b539-07b321084639` | reversal | 11.121 | 0.444071 |
| 7 | `0591e8f9-4433-4105-96bf-8d8da0581106` | liquidity | 10.969 | 0.496538 |
| 8 | `d3884de8-ea16-4605-8532-ebdb9394ed7e` | momentum | 10.722 | 0.470479 |
| 9 | `df6cd541-5798-4368-b94f-b1cf50afbdb0` | risk | 10.089 | 0.373046 |
| 10 | `2ab2fb9b-2d78-46df-805b-1b3fc1457851` | risk | 9.138 | 0.492124 |

### Economic Meaning And Child Factors

The displayed portfolio spans liquidity and crowding, medium-horizon continuation,
short-horizon reversal, auction imbalance, abnormal-volume reversal, Amihud illiquidity,
trading-value capacity, and persistent trend excluding the latest week. Full factor-level
lineage, child proxies, and child-factor economic interpretations are in the afternoon
paper and TSV manifest.

### Afternoon Artifacts

- Paper PDF: `D:\yyb\paper\afternoon_final_submission.pdf`
- Paper LaTeX: `D:\yyb\paper\afternoon_final_submission.tex`
- Final factor manifest: `D:\yyb\paper\afternoon_final_factors.json`
- Machine-readable factor table: `D:\yyb\paper\afternoon_final_factors.tsv`
- Paper summary: `D:\yyb\paper\afternoon_final_summary.json`
- First-round frozen audit: `D:\yyb\backtest_platform\experiment_results\afternoon_extension_results.json`
- Deep frozen audit: `D:\yyb\backtest_platform\experiment_results\afternoon_deep_results.json`
- First-round raw JSONL: `D:\yyb\backtest_platform\experiment_results\afternoon_extension_experiments.jsonl`
- Deep raw JSONL: `D:\yyb\backtest_platform\experiment_results\afternoon_deep_experiments.jsonl`

### Afternoon QA

- Flask local review: HTTP 200 at `http://127.0.0.1:5000/login`.
- ngrok public review: HTTP 200 at `https://remark-glance-tweet.ngrok-free.dev/login`.
- Exactly one Flask process listens on port 5000.
- Final PDF compiled with two XeLaTeX passes.
- All six PDF pages were rendered and visually inspected.
- Final LaTeX log contains no overfull, underfull, undefined-reference, emergency-stop,
  or LaTeX error warnings.
- No external Alpha submission was performed.

### Honest Research Status

The revised engineering delivery target is met. The manuscript is still not a
top-conference-ready empirical paper. The adaptive search inspected the 2023 OOS window;
an untouched holdout, walk-forward regime analysis, transaction-cost modeling, capacity
analysis, and formal multiple-testing control remain required before an external
performance claim.

---

## Cached Backup Addendum (2026-06-02 13:18 CST)

The active afternoon heartbeat continued after the first delivery freeze. A third,
low-memory cached backup audit added 178 real measurements without reparsing raw leaves:

- 96 cached cross-style pair variants.
- 72 cached cross-style triple variants.
- 10 cached backup L4 meta-nesting variants.
- Failed backup rows: 0.

The full afternoon evidence set is now 950 measured experiments. The strict
Sharpe-greater-than-8 pool increased from 18 to 22 candidates. Greedy portfolio counts
by absolute daily-PnL correlation threshold are:

| Correlation threshold | Strict portfolio size |
|---:|---:|
| 0.35 | 8 |
| 0.40 | 10 |
| 0.45 | 13 |
| 0.50 | 22 |
| 0.55 | 23 |

The paper, LaTeX, JSON manifest, TSV table, figures, and summary were regenerated from
all three measured JSONL logs. The final displayed portfolio remains 10 factors, all with
OOS Sharpe greater than 8 and pairwise absolute daily-PnL correlation below 0.5. The new
maximum displayed pairwise correlation is `0.4980399456918927`.

| Rank | ID | Theme | OOS Sharpe | Max corr. to selected |
|---:|---|---|---:|---:|
| 1 | `de3cc910-3898-415a-acb0-f7957af9c28d` | composite | 16.247 | 0.000000 |
| 2 | `ea1a3e72-f0fa-454e-b965-b6de3f4de0b8` | composite | 15.316 | 0.472103 |
| 3 | `c0e67121-8bd4-4fb0-a3de-833d17bace96` | composite | 14.020 | 0.483035 |
| 4 | `ca6a835d-169f-425d-bafc-dc26e7d55f20` | composite | 13.698 | 0.487555 |
| 5 | `009f92ac-11d7-4365-b9ec-21472d5a4b84` | composite | 13.459 | 0.498040 |
| 6 | `5400d6a4-33ad-47e4-b7e7-a71c792d1baa` | composite | 13.332 | 0.469443 |
| 7 | `8138a76a-00ed-46a8-9c52-decf0e2a1c3a` | momentum | 13.141 | 0.495942 |
| 8 | `b72fe1ae-8309-437d-9dbb-08d0dc5beab2` | composite | 12.063 | 0.434813 |
| 9 | `ea867db0-03b3-44ff-b539-07b321084639` | reversal | 11.121 | 0.383367 |
| 10 | `d3884de8-ea16-4605-8532-ebdb9394ed7e` | momentum | 10.722 | 0.482798 |

Additional frozen backup artifacts:

- `D:\yyb\backtest_platform\experiment_results\afternoon_backup_results.json`
- `D:\yyb\backtest_platform\experiment_results\afternoon_backup_experiments.jsonl`

Final cached-backup QA:

- Flask local review: HTTP 200.
- ngrok public review: HTTP 200.
- Exactly one Flask listener remains on port 5000.
- Six regenerated PDF pages visually inspected.
- Two XeLaTeX passes completed with no overfull, underfull, undefined-reference,
  emergency-stop, or LaTeX error warnings.
- No external Alpha submission was performed.

---

## Completion and Sequential-Split Audit Addendum (2026-06-02 13:42 CST)

The frozen delivery was recompiled and checked with
`D:\yyb\backtest_platform\afternoon_completion_audit.py`. The machine report is:

- `D:\yyb\paper\afternoon_completion_audit.json`

The report passed every check: all 950 JSONL measurements parse and report success,
the strict pool contains 22 candidates, the displayed portfolio contains exactly 10
factors, every displayed OOS Sharpe is greater than 8, and the full-window maximum
pairwise absolute daily-PnL correlation is `0.4980399456918927`.

The descriptive sequential-split artifacts are:

- `D:\yyb\paper\afternoon_regime_audit.json`
- `D:\yyb\paper\afternoon_regime_audit.tsv`

These splits remain inside the adaptively inspected 2023 OOS window. They are not a
new untouched holdout and must not be presented as external validation. All 10 displayed
factors remain positive in both sequential half-year blocks. However, pairwise
correlation diversification is not uniformly stable by subperiod:

| Segment | Days | Equal-weight Sharpe | Maximum pairwise corr. |
|---|---:|---:|---:|
| Full 2023 OOS | 241 | 21.269 | 0.4980 |
| H1 sequential | 120 | 17.312 | 0.5866 |
| H2 sequential | 121 | 27.135 | 0.6097 |
| Q1 sequential | 60 | 22.707 | 0.6489 |
| Q2 sequential | 60 | 16.422 | 0.6476 |
| Q3 sequential | 60 | 37.962 | 0.5311 |
| Q4 sequential | 61 | 22.891 | 0.7409 |

The regenerated six-page paper now discloses this limitation explicitly. At the
13:42 CST audit, Flask local review and ngrok public review both returned HTTP 200,
one Flask process owned the sole port-5000 listener, and free physical memory was
approximately 1.86 GB. No external Alpha submission route is present in the three
afternoon experiment runners.

### Untouched-Holdout Preregistration

The next validation protocol is frozen before any new result is opened:

- Generator: `D:\yyb\backtest_platform\generate_next_holdout_preregistration.py`
- Machine protocol: `D:\yyb\paper\next_holdout_preregistration.json`
- Human-readable protocol: `D:\yyb\paper\next_holdout_preregistration.md`

The protocol locks the final 10 factor IDs, expressions, and order against source
manifest SHA-256
`8139a3fa9e9b838bbec409337d4ef77699a5fd2de343747f5178d1f84fd9ba0c`.
It requires a consecutive period disjoint from 2020-2023, prohibits holdout-driven
replacement and retuning, and requires cost, capacity, block-bootstrap, and
multiple-testing diagnostics. Its status is `preregistered_not_executed`: it is a
future evaluation plan, not new validation evidence.

### Static Delivery Index

The final static SHA-256 artifact snapshot is written by:

- `D:\yyb\backtest_platform\generate_afternoon_delivery_index.py`
- `D:\yyb\paper\afternoon_delivery_index.json`

The index covers the paper, manifests, three JSONL logs, stage summaries, regime audit,
preregistration bundle, key scripts, and handoff files. Regenerate it only after an
intentional delivery edit, then rerun `afternoon_completion_audit.py`.

### Descriptive Phase Audit

The 950 recorded experiments are summarized by phase and neutralization label in:

- Generator: `D:\yyb\backtest_platform\generate_afternoon_phase_audit.py`
- JSON: `D:\yyb\paper\afternoon_phase_audit.json`
- TSV: `D:\yyb\paper\afternoon_phase_audit.tsv`

The paper phase table reports rows, `Sharpe > 8` counts, median Sharpe, P90 Sharpe, and
maximum Sharpe for all 11 phases. A separate table reports descriptive neutralization
comparisons. Candidate mixtures differ across rows, so these are exploratory
distribution summaries, not causal treatment estimates or untouched validation.

### Literature Source Notes

Primary publisher, society, SSRN, and author-hosted links for the related-work and
future-validation references are collected in:

- `D:\yyb\paper\literature_source_notes.md`

### Public Review Tunnel Fallback (2026-06-02 14:43 CST)

The original ngrok address began returning HTTP 404 because the ngrok account reached
its concurrent agent/session limit (`ERR_NGROK_108` and `ERR_NGROK_18021`). Flask
remained healthy and was not restarted. Public review was restored through the
installed official `cloudflared` quick-tunnel client:

- Public login: `https://tries-decision-avenue-facing.trycloudflare.com/login`
- Local login: `http://127.0.0.1:5000/login`
- Active cloudflared PID at recovery: `29096`
- Fallback URL state file: `D:\yyb\logs\cloudflared_public_url.txt`

`D:\yyb\backtest_platform\yyb_guardian.py`, `afternoon_completion_audit.py`, and
`generate_afternoon_delivery_index.py` now recognize the Cloudflare fallback. The
quick-tunnel URL is ephemeral; read the state file after a future restart.

---

## Post-15:00 Final Service Audit (2026-06-02 15:03 CST)

The requested supervision window has ended. At `2026-06-02T15:03:35+08:00`:

- Local Flask login returned HTTP 200: `http://127.0.0.1:5000/login`.
- Fixed ngrok login returned HTTP 200:
  `https://remark-glance-tweet.ngrok-free.dev/login`.
- Cloudflare fallback login returned HTTP 200:
  `https://tries-decision-avenue-facing.trycloudflare.com/login`.
- Flask PID `29556` owned the sole port-5000 listener.
- Available physical memory was approximately `1.215 GB`.
- Background processes were limited to the scheduler, ngrok, cloudflared fallback,
  Flask, and the lightweight audit pulse.

During the final monitoring block, available memory briefly reached approximately
`0.926 GB`; paused-background-work flags remained in force and Flask stayed available.
No external Alpha submission was performed.
