"""Standalone compute worker — runs EW/ICIR/Ridge in subprocess. All memory guaranteed released on exit."""
import sys, os, json, traceback, time, gc, math
import numpy as np


class _NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.floating, np.float16, np.float32, np.float64)):
            v = float(obj)
            return None if math.isnan(v) or math.isinf(v) else v
        if isinstance(obj, (np.integer, np.bool_)):
            return int(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        try:
            return float(obj)
        except (TypeError, ValueError):
            pass
        return super().default(obj)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '模型'))

def main():
    if len(sys.argv) < 2:
        print("Usage: compute_worker.py <task_file>", file=sys.stderr)
        sys.exit(1)
    task_file = sys.argv[1]
    result_file = task_file.replace('.json', '_result.json')

    try:
        with open(task_file, 'r', encoding='utf-8') as f:
            task = json.load(f)
        data = task['data']

        from app import app as flask_app, get_engine, parse_expression, _compute_metrics_from_result, _add_to_history, _to_json_safe, _load_cached_lgb, _economic_group

        with flask_app.app_context():
            pipeline, engine, fc = get_engine()
            kind = task.get('kind', 'superalpha')

            # ---- Helper: OOS date boundary ----
            date_keys = sorted(pipeline.date_to_idx.keys())
            def _first_trading_day_after(d):
                for dk in date_keys:
                    if dk >= d: return pipeline.date_to_idx[dk]
                return None
            def _last_trading_day_before(d):
                for dk in reversed(date_keys):
                    if dk < d: return pipeline.date_to_idx[dk]
                return None

            # ============================================================
            # SINGLE FACTOR BACKTEST with IS/OOS split
            # ============================================================
            if kind == 'backtest':
                expression = data['expression'].strip()
                neutralize = data.get('neutralize', 'none')
                factor_arr = parse_expression(expression, pipeline, fc)
                if factor_arr is None:
                    raise ValueError(f'parse failed: {expression}')

                # IS period: 2020-01-02 to last day before 2023
                t0_is = pipeline.date_to_idx['2020-01-02']
                t1_is = _last_trading_day_before('2023-01-01') + 1
                # OOS period: first day of 2023 to 2023-12-29
                t0_oos = _first_trading_day_after('2023-01-01')
                t1_oos = min(pipeline.date_to_idx['2023-12-29'] + 1, pipeline.n_dates)

                label = pipeline.fields['Label']
                univ = pipeline.universe_mask

                # Market cap neutralization
                if neutralize == 'market_cap':
                    adjf = np.clip(np.where(np.isnan(pipeline.fields['I_D_ADJFACTOR']), 1.0,
                                        pipeline.fields.get('I_D_ADJFACTOR', np.ones_like(factor_arr[0]))), 0.01, 100)
                    mcap = pipeline.fields['I_D_CLOSE_ORI'] * adjf * pipeline.fields.get('I_D_TOTAL_SHARES', pipeline.fields.get('I_D_SHARE_LIQA', np.ones_like(factor_arr[0])))
                    f_is = np.asarray(factor_arr[t0_is:t1_is], dtype=np.float32)
                    f_oos = np.asarray(factor_arr[t0_oos:t1_oos], dtype=np.float32)
                    for t_range, t0, t1, f_out in [('IS', t0_is, t1_is, f_is), ('OOS', t0_oos, t1_oos, f_oos)]:
                        mcap_t = np.asarray(mcap[t0:t1], dtype=np.float64)
                        for t in range(f_out.shape[0]):
                            v = ~np.isnan(f_out[t]) & ~np.isnan(mcap_t[t]) & (mcap_t[t] > 0)
                            if v.sum() < 100: continue
                            log_mcap = np.log(mcap_t[t][v])
                            gids = np.floor(np.digitize(log_mcap, np.percentile(log_mcap, np.arange(0, 101, 10))) / 10).astype(int)
                            cv = f_out[t][v].copy()
                            for g in np.unique(gids):
                                gm = gids == g
                                if gm.sum() >= 10:
                                    cv[gm] = cv[gm] - np.nanmean(cv[gm])
                            f_out[t][v] = cv
                else:
                    f_is = np.asarray(factor_arr[t0_is:t1_is], dtype=np.float32)
                    f_oos = np.asarray(factor_arr[t0_oos:t1_oos], dtype=np.float32)

                # IS evaluation
                res_is = engine.full_evaluation(f_is, univ[t0_is:t1_is], label=label[t0_is:t1_is])
                m_is = _compute_metrics_from_result(f_is, label[t0_is:t1_is], univ[t0_is:t1_is], res_is)
                # OOS evaluation
                res_oos = engine.full_evaluation(f_oos, univ[t0_oos:t1_oos], label=label[t0_oos:t1_oos])
                m_oos = _compute_metrics_from_result(f_oos, label[t0_oos:t1_oos], univ[t0_oos:t1_oos], res_oos)

                # Merge: OOS as primary, IS metrics prefixed
                metrics = {k:v for k,v in m_oos.items() if k not in ('_factor_array','_direction')}
                for k in ['pearson_ic','sharpe','icir','fitness','annual_excess','returns','max_drawdown','turnover','margin_bps','win_rate','pnl_series']:
                    v = m_is.get(k)
                    if v is not None:
                        metrics['is_'+k] = v
                metrics['oos_pearson_ic'] = m_oos.get('pearson_ic')
                metrics['_neutralize'] = neutralize
                _add_to_history(expression, metrics, 'alpha', name=expression[:40])

                answer = {'success': True, 'metrics': metrics}
                del f_is, f_oos, factor_arr; gc.collect()
                _write_result(result_file, {'status': 'done', 'progress': 100, 'result': _to_json_safe(answer)})
                return

            # ============================================================
            # SUPERALPHA (EW/ICIR/Ridge combos) — OOS only
            # ============================================================
            expressions = data['expressions']
            weights = data['weights']
            neutralize = data.get('neutralize', 'none')
            sub_alpha_limit = data.get('sub_alpha_limit', len(expressions))
            method = data.get('method', 'equal')
            oos_only = data.get('oos_only', False)
            cached_expr_map = data.get('cached_expr_map', {})

            # Determine time range
            date_keys = sorted(pipeline.date_to_idx.keys())
            if oos_only:
                t0 = None
                for d in date_keys:
                    if d >= '2023-01-01':
                        t0 = pipeline.date_to_idx[d]
                        break
                if t0 is None: t0 = pipeline.date_to_idx[date_keys[-1]]
            else:
                t0 = pipeline.date_to_idx['2020-01-02']
            t1 = min(pipeline.date_to_idx['2023-12-29'] + 1, pipeline.n_dates)
            label_train = pipeline.fields['Label'][t0:t1]
            univ_train = pipeline.universe_mask[t0:t1]

            n_dates, n_stocks = label_train.shape
            combined = np.zeros((n_dates, n_stocks), dtype=np.float32)
            weight_sum = np.zeros((n_dates, n_stocks), dtype=np.float32)
            sub_results = []
            skipped_features = []
            valid_count = 0

            for i, expr in enumerate(expressions):
                try:
                    # Handle cached matrix from lookup map
                    if str(i) in cached_expr_map:
                        cache_path = cached_expr_map[str(i)]
                        matrix = np.load(cache_path)
                        f_train = np.asarray(matrix[t0:t1], dtype=np.float32)
                    else:
                        factor = parse_expression(expr, pipeline, fc)
                        if factor is None or not np.issubdtype(factor.dtype, np.floating):
                            skipped_features.append({'expression': str(expr)[:100], 'reason': f'non-numeric dtype {factor.dtype if factor is not None else \"None\"}'})
                            continue
                        f_train = np.asarray(factor[t0:t1], dtype=np.float32)
                        del factor
                    if f_train.shape != combined.shape:
                        raise ValueError(f'factor shape mismatch: {f_train.shape}')
                    f_mean = np.nanmean(f_train, axis=1, keepdims=True)
                    f_std = np.nanstd(f_train, axis=1, keepdims=True) + 1e-10
                    fz = (f_train - f_mean) / f_std
                    valid = np.isfinite(fz)
                    if not np.any(valid):
                        raise ValueError('all-missing factor')
                    w = float(weights[i])
                    combined[valid] += w * fz[valid]
                    weight_sum[valid] += w
                    valid_count += 1
                    if len(sub_results) < sub_alpha_limit:
                        result = engine.full_evaluation(f_train, univ_train, label=label_train)
                        metrics = _compute_metrics_from_result(f_train, label_train, univ_train, result)
                        sub_results.append({
                            'expression': expr, 'weight': round(w,4),
                            'metrics': {k:v for k,v in metrics.items() if k not in ('_factor_array','_direction','ic_series','pnl_series')},
                            'ic_series': metrics.get('ic_series',[]), 'pnl_series': metrics.get('pnl_series',[]),
                        })
                    del f_train, fz, valid, f_mean, f_std
                    if valid_count % 10 == 0: gc.collect()
                except Exception as e:
                    skipped_features.append({'expression': str(expr)[:100], 'reason': str(e)[:180]})
                    gc.collect()
                    continue

            valid_weight = np.isfinite(weight_sum) & (np.abs(weight_sum) > 1e-12)
            if valid_count < 1 or not np.any(valid_weight):
                raise ValueError('no valid SuperAlpha features after parsing')
            combined[valid_weight] = combined[valid_weight] / weight_sum[valid_weight]
            combined[~valid_weight] = np.nan
            del weight_sum; gc.collect()

            # Market cap neutralization
            if neutralize == 'market_cap':
                from scipy import stats
                adjf = np.clip(np.where(np.isnan(pipeline.fields['I_D_ADJFACTOR']), 1.0,
                                    pipeline.fields.get('I_D_ADJFACTOR', np.ones_like(combined[0]))), 0.01, 100)
                mcap = pipeline.fields['I_D_CLOSE_ORI'] * adjf * pipeline.fields.get('I_D_TOTAL_SHARES', pipeline.fields.get('I_D_SHARE_LIQA', np.ones_like(combined[0])))
                mcap_train = mcap[t0:t1]
                for t in range(combined.shape[0]):
                    valid = ~np.isnan(combined[t]) & ~np.isnan(mcap_train[t])
                    if valid.sum() < 100: continue
                    log_mcap = np.log(np.maximum(mcap_train[t, valid], 1))
                    gids = np.floor(np.digitize(log_mcap, np.percentile(log_mcap, np.arange(0,101,10)))/10).astype(int)
                    cv = combined[t, valid].copy()
                    for g in np.unique(gids):
                        gm = gids == g
                        if gm.sum() >= 10: cv[gm] = cv[gm] - np.nanmean(cv[gm])
                    combined[t, valid] = cv

            combined_result = engine.full_evaluation(combined, univ_train, label=label_train)
            combined_metrics = _compute_metrics_from_result(combined, label_train, univ_train, combined_result)
            combined_metrics_clean = {k:v for k,v in combined_metrics.items() if k not in ('_factor_array','_direction')}

            response = {
                'success': True, 'type': 'superalpha',
                'n_requested_factors': len(expressions), 'n_valid_factors': valid_count,
                'n_skipped_features': len(skipped_features), 'skipped_features': skipped_features[:50],
                'sub_alphas_truncated': max(0, valid_count - len(sub_results)),
                'combined_metrics': combined_metrics_clean, 'sub_alphas': sub_results,
            }

            # Build expression for history saving
            expr_strs = [e if isinstance(e,str) else ('__lgb_cached__') for e in expressions]
            if method == 'equal':
                combined_expression = 'superalpha(' + ' + '.join(expr_strs) + ')'
            elif method in ('icir','ridge'):
                weighted = [f'{round(w,4)}*{e}' for w,e in zip(weights, expr_strs)]
                combined_expression = f'superalpha[{method}](' + ' + '.join(weighted) + ')'
            else:
                combined_expression = 'superalpha(' + ' + '.join(expr_strs) + ')'
            combined_metrics['_neutralize'] = neutralize
            history_id = _add_to_history(combined_expression, combined_metrics, 'superalpha')

            # Cache combined matrix for reuse (same pattern as LGB)
            if history_id:
                try:
                    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache'), exist_ok=True)
                    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', f'ew_{history_id}.npy')
                    np.save(cache_path, combined)
                except Exception:
                    pass

            del combined; gc.collect()
            _write_result(result_file, {'status': 'done', 'progress': 100, 'result': _to_json_safe(response)})

    except Exception as e:
        traceback.print_exc()
        _write_result(result_file, {'status': 'error', 'progress': 0, 'error': str(e)[:500]})


def _write_result(path, data):
    data['updated_at'] = time.time()
    with open(path + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, cls=_NumpyEncoder)
    os.replace(path + '.tmp', path)


if __name__ == '__main__':
    main()
