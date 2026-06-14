# Next Untouched-Holdout Preregistration

Generated: `2026-06-02T14:02:26`

Status: `preregistered_not_executed`

This document freezes the next evaluation protocol. It does not contain new holdout
measurements. The 2023 OOS window was already inspected adaptively and cannot serve as
external validation.

## Frozen Portfolio

| Rank | ID | Theme | Inspected 2023 OOS Sharpe | Max corr. to selected |
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

## Untouched-Holdout Rules

1. Use a consecutive period disjoint from 2020-2023.
2. Open results only after recording all frozen expressions without retuning.
3. Do not replace failed factors using the untouched holdout.
4. Report raw, cost-adjusted, capacity, block-bootstrap, and multiple-testing results.
5. Keep the workflow local and do not submit any external Alpha.

The machine-readable protocol is `D:\yyb\paper\next_holdout_preregistration.json`.
