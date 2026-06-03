"""Persistent Serveo tunnel — auto-reconnect on failure."""
import subprocess, time, re

def start_tunnel():
    cmd = [
        'ssh', '-o', 'StrictHostKeyChecking=no',
        '-o', 'ServerAliveInterval=30',
        '-o', 'ServerAliveCountMax=3',
        '-o', 'ExitOnForwardFailure=yes',
        '-R', '80:127.0.0.1:5000',
        'serveo.net'
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    url = None
    start = time.time()
    # Read initial output to get URL
    while time.time() - start < 15:
        line = proc.stdout.readline()
        if not line and proc.poll() is not None:
            break
        print(line, end='')
        m = re.search(r'https://([\w-]+\.serveo[a-z]*\.\w+)', line)
        if m:
            url = m.group(0)
    return proc, url

def main():
    print('Starting persistent Serveo tunnel...')
    while True:
        try:
            proc, url = start_tunnel()
            if url:
                print(f'\n=== PUBLIC URL: {url} ===\n')
            proc.wait()
        except Exception as e:
            print(f'Tunnel error: {e}')
        print('Tunnel disconnected. Reconnecting in 5s...')
        time.sleep(5)

if __name__ == '__main__':
    main()
