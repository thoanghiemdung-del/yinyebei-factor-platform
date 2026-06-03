"""Launch agent scripts in parallel."""
import subprocess, sys, glob, os

agents = sorted(glob.glob(os.path.join(os.path.dirname(__file__), 'agent*.py')))
agents = [a for a in agents if 'runner' not in a]

procs = []
for a in agents:
    p = subprocess.Popen([sys.executable, '-u', a], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    procs.append((a, p))
    print(f'Started {os.path.basename(a)} (PID {p.pid})')

for name, p in procs:
    out, _ = p.communicate()
    print(f'\n=== {os.path.basename(name)} ===')
    print(out[-500:] if len(out) > 500 else out)
