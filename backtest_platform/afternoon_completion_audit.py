#!/usr/bin/env python3
"""Verify the frozen afternoon YYB delivery from authoritative local evidence."""

import hashlib
import json
import pathlib
import re
import sqlite3
import sys
import urllib.request

import psutil


BASE = pathlib.Path(__file__).resolve().parent
ROOT = BASE.parent
PAPER = ROOT / "paper"
RESULTS = BASE / "experiment_results"
LOGS = ROOT / "logs"
OUTPUT = PAPER / "afternoon_completion_audit.json"
PUBLIC_INSPECT = "http://127.0.0.1:4040/api/tunnels"
FALLBACK_PUBLIC_FILE = LOGS / "cloudflared_public_url.txt"
LOCAL_LOGIN = "http://127.0.0.1:5000/login"


def status(url, timeout=8):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status
    except Exception:
        return None


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path):
    rows, errors = [], []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            rows.append(json.loads(line))
        except Exception as exc:
            errors.append({"line": index, "error": f"{type(exc).__name__}: {exc}"})
    return rows, errors


def main():
    checks = {}
    jsonl_paths = [
        RESULTS / "afternoon_extension_experiments.jsonl",
        RESULTS / "afternoon_deep_experiments.jsonl",
        RESULTS / "afternoon_backup_experiments.jsonl",
    ]
    jsonl_rows, jsonl_errors = [], {}
    for path in jsonl_paths:
        rows, errors = load_jsonl(path)
        jsonl_rows.extend(rows)
        if errors:
            jsonl_errors[str(path)] = errors
    checks["jsonl_parse"] = not jsonl_errors
    checks["experiment_rows_950"] = len(jsonl_rows) == 950
    checks["all_measured_rows_success"] = all(row.get("success") for row in jsonl_rows)

    manifest = load_json(PAPER / "afternoon_final_factors.json")
    factors = manifest["factors"]
    matrix = manifest["correlation_matrix"]
    pairwise = [
        abs(float(matrix[i][j]))
        for i in range(len(matrix))
        for j in range(i)
    ]
    max_corr = max(pairwise) if pairwise else 0.0
    checks["strict_available_at_least_10"] = int(manifest["strict_available_count"]) >= 10
    checks["displayed_exactly_10"] = len(factors) == 10 == int(manifest["displayed_count"])
    checks["all_displayed_sharpe_gt_8"] = all(float(row["sharpe"]) > 8.0 for row in factors)
    checks["all_displayed_pairwise_abs_corr_lt_0_5"] = max_corr < 0.5
    checks["manifest_max_corr_matches_matrix"] = (
        abs(float(manifest["maximum_pairwise_corr"]) - max_corr) < 1e-12
    )

    summary = load_json(PAPER / "afternoon_final_summary.json")
    checks["summary_rows_match_jsonl"] = int(summary["experiment_rows"]) == len(jsonl_rows)
    checks["summary_strict_matches_manifest"] = (
        int(summary["strict_available_count"]) == int(manifest["strict_available_count"])
    )

    phase_json = PAPER / "afternoon_phase_audit.json"
    phase_tsv = PAPER / "afternoon_phase_audit.tsv"
    phase_audit = load_json(phase_json)
    checks["phase_audit_artifacts_exist"] = phase_json.exists() and phase_tsv.exists()
    checks["phase_audit_rows_match_jsonl"] = (
        int(phase_audit["experiment_rows"]) == len(jsonl_rows) == 950
    )
    checks["phase_audit_all_rows_success"] = phase_audit["all_rows_success"] is True
    checks["phase_audit_contains_11_phases"] = int(phase_audit["phase_count"]) == 11
    checks["phase_audit_discloses_not_untouched_validation"] = (
        "not untouched validation" in phase_audit["note"].lower()
    )

    regime_json = PAPER / "afternoon_regime_audit.json"
    regime_tsv = PAPER / "afternoon_regime_audit.tsv"
    regime = load_json(regime_json)
    regime_segments = regime["segments"]
    regime_splits = regime["factor_half_splits"]
    full_segment = next(
        segment for segment in regime_segments if segment["segment"] == "Full 2023 OOS"
    )
    subperiod_peak_corr = max(
        float(segment["maximum_pairwise_abs_daily_pnl_corr"])
        for segment in regime_segments
        if segment["segment"] != "Full 2023 OOS"
    )
    checks["regime_split_artifacts_exist"] = regime_json.exists() and regime_tsv.exists()
    checks["regime_split_note_discloses_not_untouched_holdout"] = (
        "not an untouched holdout" in regime["note"].lower()
    )
    checks["regime_split_segments_complete"] = len(regime_segments) == 7
    checks["regime_split_factor_ids_match_manifest"] = (
        {row["id"] for row in regime_splits} == {row["id"] for row in factors}
    )
    checks["regime_full_corr_matches_manifest"] = (
        abs(float(full_segment["maximum_pairwise_abs_daily_pnl_corr"]) - max_corr) < 1e-6
    )

    prereg_json = PAPER / "next_holdout_preregistration.json"
    prereg_md = PAPER / "next_holdout_preregistration.md"
    prereg = load_json(prereg_json)
    checks["next_holdout_preregistration_exists"] = prereg_json.exists() and prereg_md.exists()
    checks["next_holdout_preregistration_is_not_executed"] = (
        prereg["status"] == "preregistered_not_executed"
    )
    checks["next_holdout_preregistration_hash_matches_manifest"] = (
        prereg["source_manifest_sha256"] == sha256(PAPER / "afternoon_final_factors.json")
    )
    checks["next_holdout_preregistration_ids_match_manifest"] = (
        [row["id"] for row in prereg["frozen_displayed_factors"]]
        == [row["id"] for row in factors]
    )

    delivery_index_json = PAPER / "afternoon_delivery_index.json"
    delivery_index = load_json(delivery_index_json)
    checks["delivery_index_exists"] = delivery_index_json.exists()
    checks["delivery_index_artifacts_match_current_files"] = all(
        pathlib.Path(path).exists() and sha256(pathlib.Path(path)) == digest
        for path, digest in delivery_index["artifacts"].items()
    )

    pdf = PAPER / "afternoon_final_submission.pdf"
    tex = PAPER / "afternoon_final_submission.tex"
    latex_log = PAPER / "afternoon_xelatex_pass2.log"
    warnings = re.findall(
        r"Overfull|Underfull|Undefined|Emergency stop|LaTeX Error|! ",
        latex_log.read_text(encoding="utf-8", errors="ignore"),
        flags=re.IGNORECASE,
    )
    checks["pdf_exists_and_nontrivial"] = pdf.exists() and pdf.stat().st_size > 100_000
    checks["tex_exists"] = tex.exists()
    checks["latex_log_clean"] = not warnings

    local = status(LOCAL_LOGIN)
    remote_url = None
    try:
        tunnels = json.loads(
            urllib.request.urlopen(PUBLIC_INSPECT, timeout=8).read().decode("utf-8")
        )["tunnels"]
        remote_url = tunnels[0]["public_url"] + "/login"
    except Exception:
        remote_url = None
    if not remote_url:
        try:
            remote_url = FALLBACK_PUBLIC_FILE.read_text(encoding="utf-8").strip() + "/login"
        except Exception:
            remote_url = None
    remote = status(remote_url) if remote_url else None
    checks["flask_local_http_200"] = local == 200
    checks["remote_tunnel_http_200"] = remote == 200

    app_pids = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or [])
            if (process.info.get("name") or "").lower() == "python.exe" and " app.py" in command:
                app_pids.append(process.info["pid"])
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    listener_pids = {
        connection.pid
        for connection in psutil.net_connections(kind="tcp")
        if connection.status == psutil.CONN_LISTEN and connection.laddr.port == 5000
    }
    checks["exactly_one_flask_process"] = len(app_pids) == 1
    checks["exactly_one_port_5000_listener"] = len(listener_pids) == 1
    checks["flask_process_owns_listener"] = set(app_pids) == listener_pids

    workflow_sources = [
        BASE / "run_afternoon_extension_experiments.py",
        BASE / "run_afternoon_deep_extension.py",
        BASE / "run_afternoon_backup_extension.py",
    ]
    forbidden = []
    for path in workflow_sources:
        source = path.read_text(encoding="utf-8", errors="ignore").lower()
        if "/submit" in source or "submit alpha" in source:
            forbidden.append(str(path))
    checks["workflow_contains_no_external_submit_route"] = not forbidden

    files = [
        pdf,
        tex,
        PAPER / "afternoon_final_factors.json",
        PAPER / "afternoon_final_factors.tsv",
        PAPER / "afternoon_final_summary.json",
        phase_json,
        phase_tsv,
        regime_json,
        regime_tsv,
        prereg_json,
        prereg_md,
        delivery_index_json,
        *jsonl_paths,
    ]
    report = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "passed": all(checks.values()),
        "checks": checks,
        "metrics": {
            "experiment_rows": len(jsonl_rows),
            "strict_available_count": manifest["strict_available_count"],
            "displayed_count": len(factors),
            "maximum_pairwise_abs_daily_pnl_corr": max_corr,
            "minimum_displayed_oos_sharpe": min(float(row["sharpe"]) for row in factors),
            "maximum_displayed_oos_sharpe": max(float(row["sharpe"]) for row in factors),
            "maximum_descriptive_subperiod_abs_daily_pnl_corr": subperiod_peak_corr,
            "factors_positive_in_both_descriptive_halves": sum(
                int(row["positive_halves"]) == 2 for row in regime_splits
            ),
            "local_login_status": local,
            "remote_login_status": remote,
            "remote_login_url": remote_url,
            "remote_tunnel_provider": (
                "cloudflared" if remote_url and "trycloudflare.com" in remote_url else "ngrok"
            ),
            "app_pids": app_pids,
            "port_5000_listener_pids": sorted(listener_pids),
        },
        "jsonl_parse_errors": jsonl_errors,
        "forbidden_submit_sources": forbidden,
        "sha256": {str(path): sha256(path) for path in files},
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
