"""Fix remaining empty catch blocks in dashboard.html"""
import re

path = r'D:/yyb/backtest_platform/templates/dashboard.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

replacements = 0

# Strategy: Find displayResult function span, then replace all catch(e){} within it
func_start = content.find('function displayResult(data)')
if func_start >= 0:
    # Find the function comment start
    comment_start = content.rfind('// ====', 0, func_start)
    if comment_start < 0:
        comment_start = func_start

    # Find the closing brace of displayResult
    brace_depth = 0
    in_func = False
    func_end = func_start
    for i in range(func_start, len(content)):
        ch = content[i]
        if ch == '{':
            brace_depth += 1
            in_func = True
        elif ch == '}':
            brace_depth -= 1
            if in_func and brace_depth == 0:
                func_end = i + 1
                break

    func_body = content[comment_start:func_end]
    print('displayResult function length:', len(func_body))

    # Fix all empty catch blocks within displayResult
    new_body = func_body

    # Fix the 8 metric card catches
    metrics = ['m-excess', 'm-ic', 'm-sharpe', 'm-fitness', 'm-turnover', 'm-dd', 'm-margin', 'm-winrate']
    for metric in metrics:
        old_pat = metric + " * 100).toFixed" if metric in ('m-excess', 'm-turnover', 'm-dd', 'm-winrate') else None

    # Simpler: just replace each metric card line
    for metric, label in [
        ('m-excess', 'm-excess'),
        ('m-ic', 'm-ic'),
        ('m-sharpe', 'm-sharpe'),
        ('m-fitness', 'm-fitness'),
        ('m-turnover', 'm-turnover'),
        ('m-dd', 'm-dd'),
        ('m-margin', 'm-margin'),
        ('m-winrate', 'm-winrate'),
    ]:
        # Find: try { ... metric ... } catch(e) {}
        old = "try { $('" + metric + "').textContent"
        idx = new_body.find(old)
        if idx >= 0:
            # Find the matching catch
            catch_idx = new_body.find("catch(e) {}", idx)
            if catch_idx >= 0:
                # Replace with console.error version
                new_body = new_body[:catch_idx] + "catch(e) { console.error('displayResult " + label + ":', e); }" + new_body[catch_idx + len("catch(e) {}"):]
                replacements += 1
                print('  Fixed catch for', metric)

    # Fix the chart catch blocks
    for chart_label in ['PnL chart', 'IC chart']:
        old = "} catch(e) {}\n"
        idx = new_body.find(old)
        if idx >= 0:
            new_body = new_body[:idx] + "} catch(e) { console.error('displayResult " + chart_label + ":', e); }\n" + new_body[idx + len(old):]
            replacements += 1
            print('  Fixed chart catch for', chart_label)

    content = content[:comment_start] + new_body + content[func_end:]
    print('1. displayResult fixed (' + str(replacements) + ' catches)')
else:
    print('1. displayResult NOT found')

more_r = 0

# ==========================================
# Fix startPolling catch - find by context
# ==========================================
# Look for: } catch(e) {}\n    }, 300);\n  }\n\n  // ===== RUN backtest
old_polling_pat = "} catch(e) {}\n    }, 300);\n  }\n\n  // ===== RUN backtest for a slot ====="
new_polling = "} catch(e) { console.error('startPolling error slot ' + slotIdx + ':', e); }\n    }, 300);\n  }\n\n  // ===== RUN backtest for a slot ====="
if old_polling_pat in content:
    content = content.replace(old_polling_pat, new_polling)
    more_r += 1
    print('2. startPolling catch fixed')
else:
    # Try with different indentation
    old_polling_pat2 = "} catch(e) {}\n      }, 300);\n    }\n\n    // ===== RUN backtest"
    new_polling2 = "} catch(e) { console.error('startPolling error slot ' + slotIdx + ':', e); }\n      }, 300);\n    }\n\n    // ===== RUN backtest"
    if old_polling_pat2 in content:
        content = content.replace(old_polling_pat2, new_polling2)
        more_r += 1
        print('2. startPolling catch fixed (alt indent)')
    else:
        print('2. startPolling catch NOT found - trying search...')
        # Find startPolling function and show context
        sp_idx = content.find('function startPolling')
        if sp_idx >= 0:
            # Find all catch(e){} in the next 1000 chars
            region = content[sp_idx:sp_idx+1000]
            for m in re.finditer(r'} catch\(e\) \{\}', region):
                print('   Found at offset', sp_idx + m.start())
                print('   Context:', repr(content[sp_idx + m.start() - 40 : sp_idx + m.end() + 40]))

print('Additional replacements:', more_r)
print('Total all-pass replacements:', replacements + more_r)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('dashboard.html written')
