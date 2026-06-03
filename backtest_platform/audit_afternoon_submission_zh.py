#!/usr/bin/env python3
"""Audit the supplemental Chinese delivery without changing the frozen English bundle."""

from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path


BASE = Path(__file__).resolve().parent
PAPER = Path(r"D:\yyb\paper")
MANIFEST = PAPER / "afternoon_final_factors.json"
TEX = PAPER / "afternoon_final_submission_zh.tex"
PDF = PAPER / "afternoon_final_submission_zh.pdf"
DETAIL_MD = PAPER / "afternoon_final_factor_economics_zh.md"
DETAIL_JSON = PAPER / "afternoon_final_factor_economics_zh.json"
DETAIL_TSV = PAPER / "afternoon_final_factors_zh.tsv"
AUDIT = PAPER / "afternoon_chinese_delivery_audit.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_flask_status() -> int | None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:5000/login", timeout=5) as response:
            return int(response.status)
    except Exception:
        return None


def pdf_pages() -> int:
    output = subprocess.check_output(["pdfinfo", str(PDF)], text=True, errors="replace")
    for line in output.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError("pdfinfo did not report page count")


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    details = json.loads(DETAIL_JSON.read_text(encoding="utf-8"))
    tex = TEX.read_text(encoding="utf-8")
    files = [TEX, PDF, DETAIL_MD, DETAIL_JSON, DETAIL_TSV]
    checks = {
        "supplemental_files_exist": all(path.exists() for path in files),
        "frozen_manifest_has_exactly_10_factors": len(manifest["factors"]) == 10,
        "all_frozen_factors_sharpe_gt_8": all(float(row["sharpe"]) > 8 for row in manifest["factors"]),
        "frozen_manifest_max_corr_lt_0_5": float(manifest["maximum_pairwise_corr"]) < 0.5,
        "economic_detail_has_exactly_10_factors": len(details) == 10,
        "economic_detail_contains_mechanism_and_risk": all(row.get("mechanism_zh") and row.get("risk_zh") for row in details),
        "paper_contains_project_history": "从头到尾的项目完成清单" in tex,
        "paper_contains_top_conference_boundary": "是否达到顶会标准" in tex,
        "paper_contains_child_factor_dictionary": "子因子经济含义字典" in tex,
        "paper_contains_10_factor_subsections": tex.count(r"\subsection{因子 ") == 10,
        "pdf_nontrivial": PDF.stat().st_size > 300_000,
        "pdf_pages_at_least_15": pdf_pages() >= 15,
        "flask_local_http_200": local_flask_status() == 200,
    }
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "passed": all(checks.values()),
        "checks": checks,
        "metrics": {
            "displayed_factors": len(manifest["factors"]),
            "minimum_sharpe": min(float(row["sharpe"]) for row in manifest["factors"]),
            "maximum_sharpe": max(float(row["sharpe"]) for row in manifest["factors"]),
            "maximum_pairwise_abs_daily_pnl_corr": float(manifest["maximum_pairwise_corr"]),
            "pdf_pages": pdf_pages(),
            "pdf_bytes": PDF.stat().st_size,
            "local_flask_status": local_flask_status(),
        },
        "sha256": {str(path): sha256(path) for path in files},
        "note": "Supplemental Chinese delivery audit. The English frozen evidence bundle remains untouched. No external Alpha submission is performed.",
    }
    AUDIT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if payload["passed"] else 1)


if __name__ == "__main__":
    main()
