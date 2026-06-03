import requests
import os
import time

QUEUE_FILE = r"D:/yyb/backtest_platform/factor_queue.txt"
LOGIN_URL = "http://127.0.0.1:5000/login"
API_URL = "http://127.0.0.1:5000/api/backtest"
HISTORY_URL = "http://127.0.0.1:5000/api/alpha/history"

success_count = 0
fail_count = 0
total_processed = 0

def rewrite_file(lines):
    tmp = QUEUE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(lines)
    os.replace(tmp, QUEUE_FILE)

def check_alpha_count(session):
    try:
        r = session.get(HISTORY_URL, timeout=10)
        if r.status_code == 200:
            data = r.json()
            count = data.get("count", "?")
            print(f"  [Alpha History] total: {count}")
        else:
            print(f"  [Alpha History] HTTP {r.status_code}")
    except Exception as e:
        print(f"  [Alpha History] error: {e}")

print("=" * 60)
print("Processing factor_queue.txt")
print("=" * 60)

# Create session and login
sess = requests.Session()
print("Logging in as admin...")
login_resp = sess.post(LOGIN_URL, data={"username": "admin", "password": "quant2026"}, allow_redirects=False)
if login_resp.status_code not in (200, 302):
    print(f"Login failed: HTTP {login_resp.status_code}")
    exit(1)
print("Login OK")

while True:
    if not os.path.exists(QUEUE_FILE):
        print("Queue file not found. Done.")
        break

    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        print("Queue file is empty. Done!")
        break

    first_line = lines[0].strip()
    remaining = lines[1:]

    if not first_line:
        rewrite_file(remaining)
        continue

    parts = first_line.split("|", 1)
    if len(parts) != 2:
        print(f"SKIP malformed: {first_line[:80]}")
        rewrite_file(remaining)
        fail_count += 1
        total_processed += 1
        continue

    expression, neutralization = parts[0].strip(), parts[1].strip()
    payload = {"expression": expression, "neutralization": neutralization}

    try:
        r = sess.post(API_URL, json=payload, timeout=300)
        if r.status_code == 200:
            success_count += 1
            rewrite_file(remaining)
        elif r.status_code == 401:
            # Session expired, re-login
            print("Session expired, re-logging in...")
            sess = requests.Session()
            sess.post(LOGIN_URL, data={"username": "admin", "password": "quant2026"}, allow_redirects=False)
            # Retry this item
            continue
        else:
            fail_count += 1
            resp_text = r.text[:200]
            print(f"FAIL [{total_processed+1}] HTTP {r.status_code}: {resp_text}")
            break
    except requests.exceptions.ConnectionError:
        print(f"FAIL [{total_processed+1}] Connection refused. Server running?")
        break
    except requests.exceptions.Timeout:
        print(f"FAIL [{total_processed+1}] Timeout: {expression[:60]}")
        break
    except Exception as e:
        print(f"FAIL [{total_processed+1}] {type(e).__name__}: {e}")
        break

    total_processed += 1

    if total_processed % 20 == 0:
        print(f"Progress: {total_processed} done ({success_count} ok, {fail_count} fail)")

    if total_processed % 50 == 0:
        check_alpha_count(sess)

# Final report
print()
print("=" * 60)
print(f"FINAL: processed={total_processed}, success={success_count}, fail={fail_count}")
remaining_count = 0
if os.path.exists(QUEUE_FILE):
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        remaining_count = sum(1 for _ in f)
print(f"Remaining in queue: {remaining_count}")
check_alpha_count(sess)
print("=" * 60)
