"""
Re-backtest all single factors with market cap neutralization.
Uses Flask API (subprocess compute_worker), fixes neutralized IS/OOS metrics.
"""
import requests, json, time, os, sys
from datetime import datetime

BASE = 'http://127.0.0.1:5000'
DB = r'D:\yyb\backtest_platform\backtest.db'
PY = r'python'

session = requests.Session()
r = session.post(f'{BASE}/login', data={'username': 'bot@test.com', 'password': 'test123'})
print(f'Login: {r.status_code}')

# Get all single factors
r = session.get(f'{BASE}/api/alpha/history', params={'limit': 2000})
all_records = r.json().get('records', [])
single = [r for r in all_records if r.get('type') != 'superalpha']
print(f'Total single factors to re-backtest: {len(single)}')

total = 0
success = 0
errors = 0
start = datetime.now()

for i, rec in enumerate(single):
    expr = rec['expression']
    total += 1

    # Call backtest API with market_cap neutralization
    for attempt in range(3):
        try:
            r = session.post(f'{BASE}/api/backtest',
                json={'expression': expr, 'neutralize': 'market_cap'},
                timeout=120)
            if r.status_code == 200:
                data = r.json()
                if not data.get('error'):
                    success += 1
                    break
                else:
                    errors += 1
                    break
            time.sleep(2)
        except Exception:
            time.sleep(3)
    else:
        errors += 1

    elapsed = (datetime.now() - start).total_seconds()
    rate = total / elapsed if elapsed > 0 else 0
    eta = (len(single) - total) / rate / 60 if rate > 0 else 0

    if total % 50 == 0:
        print(f'[{total}/{len(single)}] OK:{success} ERR:{errors} Rate:{rate:.1f}/s ETA:{eta:.0f}min', flush=True)

elapsed = (datetime.now() - start).total_seconds()
print(f'\nDone: {success} ok, {errors} errors in {elapsed/60:.1f}min')
print(f'DB now has neutralized single factors')
"