# YYB Final Audit Handoff

Updated: 2026-06-02 02:06 CST

## Scope

This file supplements `HANDOFF_20260601.md`. It intentionally excludes credentials and
secrets. The final submission must use only measured experiment results. Do not claim the
requested ten low-correlation high-Sharpe factors unless the frozen audit proves it.

## Live Services

- Flask review service: `http://127.0.0.1:5000/login`
- Public review tunnel: `https://remark-glance-tweet.ngrok-free.dev/login`
- ngrok inspect API: `http://127.0.0.1:4040/api/tunnels`
- Flask, ngrok, the scheduler, the audit runner, the audit supervisor, and the final
  submission supervisor are expected to remain live until delivery.
- `D:\yyb\logs\combo_builder_paused.flag` is intentional while the final audit owns the
  single experiment slot.
- `D:\yyb\logs\mining_paused.flag` is intentional. Do not restart broad mining during
  the final audit.

## Runtime Fixes Applied

- `yyb_guardian.py`
  - Uses Python 3.10 explicitly.
  - Adds 3 GB pause / 4 GB resume memory hysteresis.
  - Keeps Flask recovery separate from experiment recovery.
  - Honors the combo-builder pause flag.
- `combo_builder.py`
  - Fixes the LightGBM API contract: the backend call is synchronous and no longer
    treated as an asynchronous task id.
  - Honors the combo-builder pause flag.
- `app.py`
  - Startup cleanup only removes stale `lgb_worker.py` processes.
  - Adds explicit `none`, `market_cap`, `market_cap_regression`, `beta`, and
    `market_cap_beta` neutralization modes.
  - Persists nested lineage labels such as `superalpha_ref(...)` rather than storing
    only opaque cache placeholders.
- `yyb_scheduler_loop.py`
  - Fixes duplicate loop detection.
- Scheduled tasks `YYBSchedulerEnsure` and `YYBGuardianCheck`
  - Both now call Python 3.10 explicitly.

## Final Audit Pipeline

- Runner: `D:\yyb\backtest_platform\run_final_audit_experiments.py`
- Runner supervisor: `D:\yyb\backtest_platform\final_audit_supervisor.py`
- JSONL progress: `D:\yyb\backtest_platform\experiment_results\final_audit_experiments.jsonl`
- Frozen result: `D:\yyb\backtest_platform\experiment_results\final_audit_results.json`
- Paper generator: `D:\yyb\backtest_platform\generate_final_submission.py`
- Paper supervisor: `D:\yyb\backtest_platform\final_submission_supervisor.py`
- Final paper: `D:\yyb\paper\final_submission.tex`
- Final PDF: `D:\yyb\paper\final_submission.pdf`
- Final summary: `D:\yyb\paper\final_submission_summary.json`

The audit is API-only and keeps one pipeline resident in Flask. It records:

1. Top in-sample Sharpe baskets at N=5 and N=10.
2. Greedy baskets at correlation thresholds 0.3, 0.5, and 0.7.
3. Equal, ICIR-weighted, and inverse-volatility shrinkage combinations.
4. Five neutralization settings.
5. Exploratory style baskets and L1/L2/L3 nested combinations.
6. A frozen strict selection using OOS Sharpe greater than 10 and absolute daily-PnL
   Pearson correlation below 0.5.

## Recovery Rules

1. Keep Flask available for review. Validate local `/login` first.
2. Treat public `/login` HTTP 200 as the ngrok health criterion. Check inspect API before
   restarting ngrok because the account has a simultaneous-agent session limit.
3. Do not run `combo_builder.py`, broad mining, or a second pipeline loader in parallel
   with the audit.
4. Let the audit supervisor relaunch the runner. The runner resumes completed labels from
   the JSONL log.
5. Let the paper supervisor generate charts and compile XeLaTeX twice after the frozen
   JSON appears.
6. Never submit an external Alpha from this workflow.

## Frozen Final Truth

- Final audit frozen at `2026-06-02T00:46:52`.
- Raw measured JSONL rows: 120.
- Unique recovered summary rows: 120.
  - Confirmatory: 75.
  - Exploratory nesting: 45, with 15 rows at each of L1, L2, and L3.
- Best confirmatory configuration:
  - `top_is_sharpe_n5_icir_beta`
  - OOS Sharpe `12.882`, IC `0.0402`, fitness `18.882`, turnover `0.2709`.
- Best exploratory nesting rows:
  - L1 `nest_l1_liquidity_equal_market_cap`, Sharpe `6.252`.
  - L2 `nest_l2_equal_market_cap_beta`, Sharpe `6.356`.
  - L3 `nest_l3_equal_none`, Sharpe `10.448`.
- The requested ten-factor strict portfolio is not established.
  - Exactly one measured superalpha passes OOS Sharpe greater than 10 and the absolute
    daily-PnL pairwise correlation rule below 0.5.
  - Strict candidate `d88b1b68-7242-4f97-bc7b-3593fbd632b5`: Sharpe `13.351`,
    IC `0.0433`, fitness `18.316`, turnover `0.3161`.
  - Its historical cached expression predates lineage preservation and remains
    `superalpha(__cached__ + __cached__)`; do not invent missing leaf attribution.

## Paper Generation QA

- `generate_final_submission.py` now writes charts, LaTeX, and summary JSON from the frozen
  audit only.
- The generated paper includes strict-candidate lineage explanations and a child-factor
  economic dictionary.
- LaTeX escaping is single-pass to avoid corrupting introduced escape sequences.
- Summary JSON uses an atomic temporary-file replace.
- Long reproducibility paths use `\path{...}` and the greedy-seed table widths have been
  tightened to avoid layout overflow.
- `final_submission_supervisor.py` retries a failed generator or XeLaTeX build every
  60 seconds until the PDF exists.
- A temporary paper generated from measured partial rows passed two XeLaTeX runs and
  visual page inspection. Temporary smoke artifacts are not final evidence.
- The original frozen summary omitted measured L1 and L2 rows even though JSONL stored
  them. `rebuild_final_audit_from_jsonl.py` recovers the summary from measured JSONL rows
  only, deduplicated by label. The runner now appends L1 and L2 rows for future audits.
- The corrected final PDF was compiled twice at `2026-06-02 02:04 CST`.
- All seven final PDF pages were rendered and visually inspected. The final LaTeX log has
  no overfull, underfull, undefined-reference, emergency-stop, or error warnings.

---

## Afternoon Extension Addendum (2026-06-02)

This section is the latest handoff state. Keep the morning frozen audit for provenance,
but use the afternoon artifacts for the revised user requirement: ten measured factors
with OOS Sharpe greater than 8 and pairwise absolute daily-PnL correlation below 0.5.

### Frozen Afternoon Truth

- First-round extension frozen at `2026-06-02T11:50:13`.
- Deep extension frozen at `2026-06-02T12:42:04`.
- Paper regenerated and compiled twice after the deep freeze.
- Afternoon measured rows: 772.
  - Residualized near-threshold: 116.
  - Cross-style bridge: 270.
  - Style anchor: 60.
  - Nested style anchor: 20.
  - Cross-style offset: 60.
  - Weighted cross-style: 96.
  - Deep pair/triple nesting: 140.
  - Deep L4 meta nesting: 10.
- Failed afternoon JSONL rows: 0.
- Strict Sharpe-greater-than-8 pool: 18 measured candidates.
- Displayed portfolio: 10 measured factors.
- Maximum displayed pairwise absolute daily-PnL correlation:
  `0.49653812140608944`.
- Displayed OOS Sharpe range: `9.138` to `15.910`.

### Final Displayed Portfolio

| Rank | ID | Theme | OOS Sharpe | Max corr. |
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

### Cache-Nesting Implementation

- `app.py` accepts optional explicit weights together with `alpha_ids`.
- First-round style anchors and cross-style offsets read cached `ew_*.npy` matrices.
- Deep explicit weighted blends also use cached Alpha IDs rather than reparsing leaves.
- L3 pair/triple nesting and L4 meta nesting use the same cache path.
- The final constrained-desktop cache thresholds are `MIN_FREE_GB=0.7` and
  `RESUME_FREE_GB=1.0`. These apply to the afternoon sequential cache audit only;
  keep guardian pressure monitoring active.
- A restart race briefly left two Flask processes. The non-listening duplicate was
  removed. Final state is one Flask listener on port 5000.

### Afternoon Artifacts

- `D:\yyb\paper\afternoon_final_submission.pdf`
- `D:\yyb\paper\afternoon_final_submission.tex`
- `D:\yyb\paper\afternoon_final_factors.json`
- `D:\yyb\paper\afternoon_final_factors.tsv`
- `D:\yyb\paper\afternoon_final_summary.json`
- `D:\yyb\backtest_platform\experiment_results\afternoon_extension_results.json`
- `D:\yyb\backtest_platform\experiment_results\afternoon_deep_results.json`
- `D:\yyb\backtest_platform\experiment_results\afternoon_extension_experiments.jsonl`
- `D:\yyb\backtest_platform\experiment_results\afternoon_deep_experiments.jsonl`

### Afternoon Paper QA

- Six PDF pages rendered and visually inspected.
- Two XeLaTeX passes completed.
- Final pass has no overfull, underfull, undefined-reference, emergency-stop, or
  LaTeX error warnings.
- Paper explicitly states that the results remain an adaptive exploratory checkpoint,
  not a top-conference-ready empirical claim.
- No external Alpha submission was performed.

---

## Cached Backup Audit Addendum (2026-06-02 13:18 CST)

This is the latest handoff state. After the first afternoon freeze, the 15-minute
heartbeat continued with a low-memory cached backup audit. It added 178 real API
measurements:

- Cached cross-style pair: 96.
- Cached cross-style triple: 72.
- Cached backup L4 meta nesting: 10.
- Failed backup rows: 0.

The full afternoon audit now contains 950 measured experiments. The strict
Sharpe-greater-than-8 pool contains 22 candidates. The final displayed 10-factor
portfolio has maximum pairwise absolute daily-PnL correlation
`0.4980399456918927`.

### Latest Final Portfolio

| Rank | ID | Theme | OOS Sharpe | Max corr. |
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

### Correlation-Threshold Robustness

| Threshold | Strict pool size |
|---:|---:|
| 0.35 | 8 |
| 0.40 | 10 |
| 0.45 | 13 |
| 0.50 | 22 |
| 0.55 | 23 |

### Latest Backup Artifacts

- `D:\yyb\backtest_platform\run_afternoon_backup_extension.py`
- `D:\yyb\backtest_platform\afternoon_backup_supervisor.py`
- `D:\yyb\backtest_platform\experiment_results\afternoon_backup_results.json`
- `D:\yyb\backtest_platform\experiment_results\afternoon_backup_experiments.jsonl`

The paper generator now reads all three afternoon JSONL logs. The regenerated PDF has
six pages, passed visual QA, and has no LaTeX layout or reference warnings. Keep the
honest caveat: this remains an adaptive exploratory checkpoint, not a
top-conference-ready empirical claim.

---

## Machine Completion and Sequential-Split Audit (2026-06-02 13:42 CST)

The frozen afternoon delivery is now guarded by:

- `D:\yyb\backtest_platform\afternoon_completion_audit.py`
- `D:\yyb\paper\afternoon_completion_audit.json`
- `D:\yyb\backtest_platform\generate_afternoon_regime_audit.py`
- `D:\yyb\paper\afternoon_regime_audit.json`
- `D:\yyb\paper\afternoon_regime_audit.tsv`

The completion audit passed. It checks all 950 measured JSONL rows, the 22-candidate
strict pool, the displayed 10-factor manifest, the Sharpe-greater-than-8 and
pairwise-correlation-below-0.5 constraints, PDF/TeX artifacts, LaTeX log cleanliness,
local and public review HTTP status, sole Flask ownership of port 5000, and the absence
of an external Alpha submit route in the three afternoon runners.

The sequential-split audit is descriptive only. It stays inside the adaptively inspected
2023 OOS window and is not an untouched holdout. All ten displayed factors remain
positive in both sequential half-year blocks. Full-window maximum pairwise absolute
daily-PnL correlation is `0.4980399456918927`, but the maximum subperiod correlation is
`0.740932` in Q4. The paper discloses this non-uniform correlation stability explicitly.

At `2026-06-02 13:42:51 +08:00`, local and ngrok review endpoints both returned HTTP 200,
Flask PID `29556` owned the only port-5000 listener, and free physical memory was
approximately `1.86 GB`.

### Frozen Next-Holdout Protocol

Do not tune the displayed factors against another opened window. The future untouched
evaluation protocol is frozen in:

- `D:\yyb\backtest_platform\generate_next_holdout_preregistration.py`
- `D:\yyb\paper\next_holdout_preregistration.json`
- `D:\yyb\paper\next_holdout_preregistration.md`

The source manifest SHA-256 is
`8139a3fa9e9b838bbec409337d4ef77699a5fd2de343747f5178d1f84fd9ba0c`.
`afternoon_completion_audit.py` verifies the protocol remains unexecuted and that its
hash and ordered factor IDs match the frozen manifest.

### Static Artifact Snapshot

After any intentional delivery edit, regenerate and verify:

- `D:\yyb\backtest_platform\generate_afternoon_delivery_index.py`
- `D:\yyb\paper\afternoon_delivery_index.json`

The index hashes 31 core artifacts, including the handoff files and `yyb_guardian.py`. The completion audit
checks that every indexed artifact still matches its recorded SHA-256.

### Phase-Level Distribution Audit

The measured 950-row exploratory evidence set is summarized by phase and neutralization
label in:

- `D:\yyb\backtest_platform\generate_afternoon_phase_audit.py`
- `D:\yyb\paper\afternoon_phase_audit.json`
- `D:\yyb\paper\afternoon_phase_audit.tsv`

The completion audit requires exactly 950 rows, 11 phases, successful measured rows,
and an explicit statement that these are not untouched-validation results.

Primary publisher, society, SSRN, and author-hosted literature links are indexed in:

- `D:\yyb\paper\literature_source_notes.md`

### Cloudflare Public-Review Fallback (2026-06-02 14:43 CST)

ngrok began returning HTTP 404 after hitting account concurrent-session limits
(`ERR_NGROK_108`, `ERR_NGROK_18021`). Local Flask remained healthy. Public review is
currently available at:

- `https://tries-decision-avenue-facing.trycloudflare.com/login`

The quick-tunnel URL is stored in:

- `D:\yyb\logs\cloudflared_public_url.txt`

`yyb_guardian.py` now accepts a healthy Cloudflare fallback and can start one when ngrok
recovery fails. `afternoon_completion_audit.py` and
`generate_afternoon_delivery_index.py` report the actual remote-tunnel provider.

### Post-15:00 Service State (2026-06-02 15:03 CST)

At `2026-06-02T15:03:35+08:00`, local Flask, fixed ngrok, and Cloudflare fallback login
URLs all returned HTTP 200. Flask PID `29556` owned the sole port-5000 listener.
Available physical memory was approximately `1.215 GB`. The final monitoring block
briefly reached approximately `0.926 GB`; paused-background-work flags remained in
force and Flask stayed available.
