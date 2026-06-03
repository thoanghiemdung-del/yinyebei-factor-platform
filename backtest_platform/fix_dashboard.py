"""Fix 3 bugs in dashboard.html (Bug 1: displayResult+catches, Bug 2: handled in app.py, Bug 3: 2min limit + OK log)"""
import sys

path = r'D:/yyb/backtest_platform/templates/dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

replacements = 0

# ==========================================
# BUG 1a: Fix displayResult - update cards first, console.error in all catch blocks
# ==========================================
old = '''  // ===== Display result on SHARED metrics & charts =====
  function displayResult(data) {
    if (!data) return;
    try { $('m-excess').textContent = (data.annual_excess * 100).toFixed(2) + '%'; } catch(e) {}
    try { $('m-ic').textContent = data.pearson_ic.toFixed(4); } catch(e) {}
    try { $('m-sharpe').textContent = data.sharpe.toFixed(2); } catch(e) {}
    try { $('m-fitness').textContent = data.fitness.toFixed(2); } catch(e) {}
    try { $('m-turnover').textContent = (data.turnover * 100).toFixed(1) + '%'; } catch(e) {}
    try { $('m-dd').textContent = (data.max_drawdown * 100).toFixed(2) + '%'; } catch(e) {}
    try { $('m-margin').textContent = data.margin_bps.toFixed(1); } catch(e) {}
    try { $('m-winrate').textContent = (data.win_rate * 100).toFixed(1) + '%'; } catch(e) {}
    if (typeof Chart === 'undefined') return;
    try {
      if (pnlChart) pnlChart.destroy();
      pnlChart = new Chart($('pnl-chart').getContext('2d'), {
        type: 'line',
        data: {
          labels: (data.pnl_series || []).map(function(_, i) { return i + 1; }),
          datasets: [{ label: 'PnL %', data: data.pnl_series || [], borderColor: '#3fb950', borderWidth: 2, pointRadius: 0, fill: true, backgroundColor: 'rgba(63,185,80,0.1)' }]
        },
        options: { responsive: true, plugins: { legend: { display: false } } }
      });
    } catch(e) {}
    try {
      if (icChart) icChart.destroy();
      icChart = new Chart($('ic-chart').getContext('2d'), {
        type: 'line',
        data: {
          labels: (data.ic_series || []).map(function(_, i) { return i + 1; }),
          datasets: [{ label: 'IC', data: data.ic_series || [], borderColor: '#58a6ff', borderWidth: 1, pointRadius: 0 }]
        },
        options: { responsive: true, plugins: { legend: { display: false } } }
      });
    } catch(e) {}
  }'''

new = '''  // Bug 1 fix: ALWAYS update all 8 metric cards FIRST, chart creation wrapped in try/catch.
  // Each catch block logs errors to console -- no silent failure.
  function displayResult(data) {
    if (!data) return;
    // Phase 1: Update ALL 8 metric cards (survives even if Chart.js fails)
    try { var v = (data.annual_excess != null) ? data.annual_excess : 0; $('m-excess').textContent = (v * 100).toFixed(2) + '%'; } catch(e) { console.error('displayResult m-excess:', e); }
    try { var v = (data.pearson_ic != null) ? data.pearson_ic : 0; $('m-ic').textContent = v.toFixed(4); } catch(e) { console.error('displayResult m-ic:', e); }
    try { var v = (data.sharpe != null) ? data.sharpe : 0; $('m-sharpe').textContent = v.toFixed(2); } catch(e) { console.error('displayResult m-sharpe:', e); }
    try { var v = (data.fitness != null) ? data.fitness : 0; $('m-fitness').textContent = v.toFixed(2); } catch(e) { console.error('displayResult m-fitness:', e); }
    try { var v = (data.turnover != null) ? data.turnover : 0; $('m-turnover').textContent = (v * 100).toFixed(1) + '%'; } catch(e) { console.error('displayResult m-turnover:', e); }
    try { var v = (data.max_drawdown != null) ? data.max_drawdown : 0; $('m-dd').textContent = (v * 100).toFixed(2) + '%'; } catch(e) { console.error('displayResult m-dd:', e); }
    try { var v = (data.margin_bps != null) ? data.margin_bps : 0; $('m-margin').textContent = v.toFixed(1); } catch(e) { console.error('displayResult m-margin:', e); }
    try { var v = (data.win_rate != null) ? data.win_rate : 0; $('m-winrate').textContent = (v * 100).toFixed(1) + '%'; } catch(e) { console.error('displayResult m-winrate:', e); }
    // Phase 2: Charts (optional, wrapped in try/catch)
    if (typeof Chart === 'undefined') return;
    try {
      if (pnlChart) { pnlChart.destroy(); pnlChart = null; }
      var ctx = $('pnl-chart'); if (!ctx) return;
      pnlChart = new Chart(ctx.getContext('2d'), {
        type: 'line',
        data: {
          labels: (data.pnl_series || []).map(function(_, i) { return i + 1; }),
          datasets: [{ label: 'PnL %', data: data.pnl_series || [], borderColor: '#3fb950', borderWidth: 2, pointRadius: 0, fill: true, backgroundColor: 'rgba(63,185,80,0.1)' }]
        },
        options: { responsive: true, plugins: { legend: { display: false } } }
      });
    } catch(e) { console.error('displayResult PnL chart:', e); }
    try {
      if (icChart) { icChart.destroy(); icChart = null; }
      var ctx = $('ic-chart'); if (!ctx) return;
      icChart = new Chart(ctx.getContext('2d'), {
        type: 'line',
        data: {
          labels: (data.ic_series || []).map(function(_, i) { return i + 1; }),
          datasets: [{ label: 'IC', data: data.ic_series || [], borderColor: '#58a6ff', borderWidth: 1, pointRadius: 0 }]
        },
        options: { responsive: true, plugins: { legend: { display: false } } }
      });
    } catch(e) { console.error('displayResult IC chart:', e); }
  }'''

if old in content:
    content = content.replace(old, new)
    replacements += 1
    print('1. displayResult fixed')
else:
    print('1. displayResult NOT found - checking why...')
    idx = content.find('function displayResult(data)')
    if idx >= 0:
        snippet = content[idx:idx+200]
        print('   Found at', idx)
        print('   Snippet:', repr(snippet[:100]))
        # Try alternative approach: find the exact old string
        # Find end of function
        brace_depth = 0
        in_func = False
        end_idx = idx
        for i in range(idx, len(content)):
            ch = content[i]
            if ch == '{':
                brace_depth += 1
                in_func = True
            elif ch == '}':
                brace_depth -= 1
                if in_func and brace_depth == 0:
                    end_idx = i + 1
                    break
        print('   Function body from', idx, 'to', end_idx)
        print('   Body repr:', repr(content[idx:end_idx]))

# ==========================================
# BUG 1b: Fix startPolling catch block
# ==========================================
old2 = '''      } catch(e) {}
    }, 300);
  }

  // ===== RUN backtest for a slot ====='''
new2 = '''      } catch(e) { console.error('startPolling error slot ' + slotIdx + ':', e); }
    }, 300);
  }

  // ===== RUN backtest for a slot ====='''
if old2 in content:
    content = content.replace(old2, new2)
    replacements += 1
    print('2. startPolling catch fixed')
else:
    print('2. startPolling catch NOT found')

# ==========================================
# BUG 1c: Fix sessionStorage resume catch
# ==========================================
old3 = '''    } catch(e) {}
  }
})();

// ===== Simulation Settings Panel ====='''
new3 = '''    } catch(e) { console.error('sessionStorage resume slot ' + i + ':', e); }
  }
})();

// ===== Simulation Settings Panel ====='''
if old3 in content:
    content = content.replace(old3, new3)
    replacements += 1
    print('3. sessionStorage catch fixed')
else:
    print('3. sessionStorage catch NOT found')

# ==========================================
# BUG 1d: Fix loadSettings catch
# ==========================================
old4 = '''    }
  } catch(e) {}
}

$('settings-toggle').onclick'''
new4 = '''    }
  } catch(e) { console.error('loadSettings error:', e); }
}

$('settings-toggle').onclick'''
if old4 in content:
    content = content.replace(old4, new4)
    replacements += 1
    print('4. loadSettings catch fixed')
else:
    print('4. loadSettings catch NOT found')

# ==========================================
# BUG 1e: Fix saveSettings catch
# ==========================================
old5 = '''    $('settings-dropdown').classList.remove('show');
  } catch(e) {}
}

loadSettings();'''
new5 = '''    $('settings-dropdown').classList.remove('show');
  } catch(e) { console.error('saveSettings error:', e); }
}

loadSettings();'''
if old5 in content:
    content = content.replace(old5, new5)
    replacements += 1
    print('5. saveSettings catch fixed')
else:
    print('5. saveSettings catch NOT found')

# ==========================================
# BUG 1f: Fix stopBT catch
# ==========================================
old6 = '''      await fetch('/api/backtest/cancel/' + s.taskId, { method: 'POST' });
    } catch(e) {}
  }
  s.running = false;'''
new6 = '''      await fetch('/api/backtest/cancel/' + s.taskId, { method: 'POST' });
    } catch(e) { console.error('stopBT cancel error slot ' + slotIdx + ':', e); }
  }
  s.running = false;'''
if old6 in content:
    content = content.replace(old6, new6)
    replacements += 1
    print('6. stopBT catch fixed')
else:
    print('6. stopBT catch NOT found')

# ==========================================
# BUG 3: Add DASHBOARD INIT OK log before closing script tag
# The sessionStorage resume is already using 120000 (2 min) - correct
# ==========================================
old7 = '\n</script>\n</body>'
new7 = '\nconsole.log("DASHBOARD INIT OK");\n</script>\n</body>'
if old7 in content:
    content = content.replace(old7, new7)
    replacements += 1
    print('7. DASHBOARD INIT OK added')
else:
    print('7. closing tag NOT found')

print('Total replacements:', replacements)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('dashboard.html written successfully')
