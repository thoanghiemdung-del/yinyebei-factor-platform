"""Run factor_queue.txt backtests one at a time. Single-threaded, skips duplicates."""
import requests, time, sys, os, sqlite3, json

BASE = "http://127.0.0.1:5000"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
QUEUE_FILE = os.path.join(SCRIPT_DIR, "factor_queue.txt")
DB_PATH = os.path.join(SCRIPT_DIR, "backtest.db")

s = requests.Session()
r = s.post(f"{BASE}/login", data={"username": "admin", "password": "quant2026"}, allow_redirects=False)
if r.status_code not in (302, 200):
    print(f"Login failed: {r.status_code}")
    sys.exit(1)
print("Logged in as admin")

def already_done(expression):
    """Check if expression (or near match) already in DB."""
    try:
        db = sqlite3.connect(DB_PATH)
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM alpha_history WHERE type='alpha' AND expression=?", (expression,))
        count = cur.fetchone()[0]
        db.close()
        return count > 0
    except:
        return False

def backtest_one(expression, neutralize):
    payload = {"expression": expression, "neutralize": neutralize}
    r = s.post(f"{BASE}/api/backtest/start", json=payload)
    if r.status_code != 200:
        return {"error": f"start failed {r.status_code}: {r.text}"}
    task_id = r.json()["task_id"]

    # Poll up to 20 min (slow operators like ts_rank can take 5-10 min)
    for i in range(2400):
        time.sleep(0.5)
        r = s.get(f"{BASE}/api/backtest/status/{task_id}")
        if r.status_code != 200:
            return {"error": f"status failed {r.status_code}"}
        data = r.json()
        if data["status"] == "done":
            return data.get("result", {})
        if data["status"] == "error":
            return {"error": data.get("error", "unknown")}
    return {"error": "timeout (20 min)"}

def read_queue():
    if not os.path.exists(QUEUE_FILE):
        return []
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]

def write_queue(lines):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        for l in lines:
            f.write(l + "\n")

total = 0
good = 0
skipped = 0

while True:
    lines = read_queue()
    if not lines:
        print("Queue empty. Done.")
        break

    line = lines[0]
    parts = line.split("|")
    expression = parts[0].strip()
    neutralize = parts[1].strip() if len(parts) > 1 else "none"

    if already_done(expression):
        print(f"[SKIP] already in DB: {expression[:60]}...")
        write_queue(lines[1:])
        skipped += 1
        continue

    remaining = len(lines)
    print(f"[{total+1}/~{total+remaining}] {expression[:60]}... ", end="", flush=True)
    result = backtest_one(expression, neutralize)

    if "error" in result:
        print(f"ERROR: {result['error']}")
        # Skip failed factors, continue with next
        write_queue(lines[1:])
        continue
    else:
        ic = result.get("pearson_ic", 0) or 0
        excess = result.get("annual_excess", 0) or 0
        sharpe = result.get("sharpe", 0) or 0
        status = "OK" if abs(ic) >= 0.01 else "LOW"
        print(f"IC={ic:.4f} Ex={excess:.4f} Sh={sharpe:.3f} [{status}]")

        total += 1
        if abs(ic) >= 0.01:
            good += 1

        write_queue(lines[1:])

    time.sleep(0.3)

print(f"\nDone. Completed: {total}, |IC|>=0.01: {good}, Skipped: {skipped}")
