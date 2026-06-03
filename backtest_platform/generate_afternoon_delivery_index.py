#!/usr/bin/env python3
"""Create a static SHA-256 index for the frozen afternoon delivery."""

import datetime as dt
import hashlib
import json
import pathlib
import urllib.request

import psutil


BASE = pathlib.Path(__file__).resolve().parent
ROOT = BASE.parent
PAPER = ROOT / "paper"
RESULTS = BASE / "experiment_results"
OUTPUT = PAPER / "afternoon_delivery_index.json"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def status(url, timeout=8):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status
    except Exception:
        return None


def main():
    artifacts = [
        PAPER / "afternoon_final_submission.pdf",
        PAPER / "afternoon_final_submission.tex",
        PAPER / "afternoon_final_factors.json",
        PAPER / "afternoon_final_factors.tsv",
        PAPER / "afternoon_final_summary.json",
        PAPER / "afternoon_phase_audit.json",
        PAPER / "afternoon_phase_audit.tsv",
        PAPER / "afternoon_regime_audit.json",
        PAPER / "afternoon_regime_audit.tsv",
        PAPER / "next_holdout_preregistration.json",
        PAPER / "next_holdout_preregistration.md",
        PAPER / "literature_source_notes.md",
        RESULTS / "afternoon_extension_experiments.jsonl",
        RESULTS / "afternoon_deep_experiments.jsonl",
        RESULTS / "afternoon_backup_experiments.jsonl",
        RESULTS / "afternoon_extension_results.json",
        RESULTS / "afternoon_deep_results.json",
        RESULTS / "afternoon_backup_results.json",
        BASE / "run_afternoon_extension_experiments.py",
        BASE / "run_afternoon_deep_extension.py",
        BASE / "run_afternoon_backup_extension.py",
        BASE / "generate_afternoon_submission.py",
        BASE / "generate_afternoon_regime_audit.py",
        BASE / "generate_afternoon_phase_audit.py",
        BASE / "generate_next_holdout_preregistration.py",
        BASE / "generate_afternoon_delivery_index.py",
        BASE / "afternoon_completion_audit.py",
        BASE / "yyb_guardian.py",
        ROOT / "FINAL_DELIVERY_20260602.md",
        ROOT / "HANDOFF_FINAL_AUDIT_20260601.md",
        ROOT / "HANDOFF_20260601.md",
    ]
    missing = [str(path) for path in artifacts if not path.exists()]
    if missing:
        raise FileNotFoundError(f"missing delivery artifacts: {missing}")

    remote_url = None
    try:
        tunnels = json.loads(
            urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=8)
            .read()
            .decode("utf-8")
        )["tunnels"]
        remote_url = tunnels[0]["public_url"] + "/login"
    except Exception:
        remote_url = None
    if not remote_url:
        try:
            remote_url = (
                (ROOT / "logs" / "cloudflared_public_url.txt").read_text(encoding="utf-8").strip()
                + "/login"
            )
        except Exception:
            remote_url = None

    app_pids = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or [])
            if (process.info.get("name") or "").lower() == "python.exe" and " app.py" in command:
                app_pids.append(process.info["pid"])
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
    listener_pids = sorted(
        {
            connection.pid
            for connection in psutil.net_connections(kind="tcp")
            if connection.status == psutil.CONN_LISTEN and connection.laddr.port == 5000
        }
    )

    report = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "purpose": "Static integrity snapshot for the frozen afternoon exploratory delivery.",
        "artifacts": {str(path): sha256(path) for path in artifacts},
        "health_snapshot": {
            "local_login_status": status("http://127.0.0.1:5000/login"),
            "remote_login_url": remote_url,
            "remote_login_status": status(remote_url) if remote_url else None,
            "remote_tunnel_provider": (
                "cloudflared" if remote_url and "trycloudflare.com" in remote_url else "ngrok"
            ),
            "available_memory_gb": round(psutil.virtual_memory().available / 1024**3, 3),
            "flask_app_pids": app_pids,
            "port_5000_listener_pids": listener_pids,
        },
        "note": "No external Alpha submission is performed by this indexer.",
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "artifact_count": len(artifacts),
                "health_snapshot": report["health_snapshot"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
