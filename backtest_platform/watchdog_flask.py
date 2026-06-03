#!/usr/bin/env python3
"""Watchdog — auto-restart Flask + Ngrok if down."""
import subprocess, time, datetime, os, urllib.request

FLASK_DIR = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(FLASK_DIR, '..', 'logs', 'watchdog.log')
NGROK_EXE = 'D:/yyb/ngrok.exe'
NGROK_URL = 'remark-glance-tweet.ngrok-free.dev'
os.makedirs(os.path.dirname(LOG), exist_ok=True)

def log(msg):
    ts = datetime.datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f: f.write(line + '\n')

def is_flask_alive():
    try:
        urllib.request.urlopen('http://127.0.0.1:5000/api/fields', timeout=5)
        return True
    except:
        return False

def is_ngrok_alive():
    try:
        urllib.request.urlopen(f'https://{NGROK_URL}/api/fields', timeout=5)
        return True
    except:
        return False

def start_flask():
    log("Starting Flask...")
    subprocess.Popen(['python', 'app.py'], cwd=FLASK_DIR,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5)
    return is_flask_alive()

def start_ngrok():
    log("Starting Ngrok...")
    subprocess.Popen([NGROK_EXE, 'http', '5000', f'--url={NGROK_URL}'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(5)
    return is_ngrok_alive()

log("Watchdog started (Flask + Ngrok). Checking every 60s.")
while True:
    if not is_flask_alive():
        log("Flask DOWN! Restarting...")
        if start_flask():
            log("Flask restarted OK")
        else:
            log("Flask restart FAILED!")
    if not is_ngrok_alive():
        log("Ngrok DOWN! Restarting...")
        if start_ngrok():
            log("Ngrok restarted OK")
        else:
            log("Ngrok restart FAILED!")
    time.sleep(60)
