import json
import os
import sqlite3

DB = "D:/yyb/backtest_platform/backtest.db"
JSONL = "D:/yyb/backtest_platform/results.jsonl"

conn = sqlite3.connect(DB)
conn.execute("PRAGMA journal_mode=DELETE")
conn.execute("PRAGMA busy_timeout=5000")

before = conn.execute("SELECT COUNT(*) FROM alpha_history").fetchone()[0]
inserted = 0
seen = set()

with open(JSONL, "r", encoding="utf-8") as f:
    for line in f:
        if not line.strip():
            continue
        row = json.loads(line)
        expr = row.get("expression", "").strip()
        if not expr or expr in seen:
            continue
        seen.add(expr)
        cur = conn.execute(
            "INSERT OR IGNORE INTO alpha_history "
            "(id, name, expression, timestamp, type, metrics_json, pnl_json, ic_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row["id"],
                row["name"],
                row["expression"],
                row["timestamp"],
                row["type"],
                row["metrics_json"],
                row["pnl_json"],
                row["ic_json"],
            ),
        )
        inserted += cur.rowcount

conn.commit()
after = conn.execute("SELECT COUNT(*) FROM alpha_history").fetchone()[0]
for ext in ("-wal", "-shm"):
    try:
        os.remove(DB + ext)
    except FileNotFoundError:
        pass
conn.close()

print(f"before={before} json_unique={len(seen)} inserted={inserted} after={after}")
