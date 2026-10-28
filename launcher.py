"""Start bundled Windows services; no external Python/Node or absolute paths needed."""
from pathlib import Path
import argparse, json, os, signal, socket, subprocess, sys, time, urllib.request, webbrowser
ROOT = Path(__file__).resolve().parent
API_PORT, WEB_PORT = 18000, 13000
HEALTH_KEYS = {'status', 'llm_provider', 'embedding_provider', 'asr_installed', 'asr_model'}


def listener_pid(port):
    """Find the PID listening on a local TCP port via netstat, or None."""
    encoding = 'mbcs' if sys.platform == 'win32' else 'utf-8'
    try:
        result = subprocess.run(['netstat', '-ano', '-p', 'tcp'], capture_output=True, timeout=10)
        text = result.stdout.decode(encoding, 'replace')
    except (OSError, subprocess.SubprocessError):
        return None
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 5 and fields[1] == f'127.0.0.1:{port}' and fields[3] == 'LISTENING':
            try:
                return int(fields[4])
            except ValueError:
                return None
    return None


def answers_like_backend(port):
    """True when the port serves this package's /api/health payload shape."""
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health', timeout=2) as response:
            body = json.loads(response.read().decode('utf-8', 'replace'))
    except (OSError, ValueError):
        return False
    return isinstance(body, dict) and HEALTH_KEYS <= set(body)


def answers_like_frontend(port):
    """True when the port serves this package's compiled Next.js UI."""
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2) as response:
            body = response.read(65536).decode('utf-8', 'replace')
    except (OSError, ValueError):
        return False
    return '/_next/' in body


def stop_stale_listener(port):
    """Terminate a leftover listener from an earlier run of this same package."""
    pid = listener_pid(port)
    if pid is None or pid == os.getpid():
        return None
    subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True, timeout=10)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', port))
            return pid
        except OSError:
            time.sleep(.25)
    return None


def free_port(port):
    """Free a required port, stopping only leftovers of this same package."""
    try:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', port))
        return
    except OSError:
        pass
    if answers_like_backend(port) or answers_like_frontend(port):
        pid = stop_stale_listener(port)
        if pid is not None:
            print(f'Cleared leftover SpeakLink service on port {port} (PID {pid}) from an earlier run.', flush=True)
            return
    raise RuntimeError(f'Port {port} is occupied by another program. Close that program and try again.') from None


def pick_asr_model():
    """Prefer the best bundled CT2 model measured on our evaluation set; fall back to base.

    Benchmarks (15 clean-sentence set, CPU int8): turbo 1.06% CER, small 1.59%, base 7.41%.
    Turbo is roughly half the real-time speed of small but fixes literary/low-frequency
    vocabulary errors. Power users can set KNOWGPT_ASR_MODEL explicitly to override.
    """
    for name in ('whisper-large-v3-turbo', 'whisper-small', 'whisper-base'):
        candidate = ROOT / 'models' / name
        if (candidate / 'model.bin').is_file():
            return candidate
    return ROOT / 'models' / 'whisper-base'


def wait_ready(url, child, timeout=90):
    """Wait for readiness while detecting a failed child promptly."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError('Service exited. Inspect data/logs for details.')
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, TimeoutError):
            pass
        time.sleep(.4)
    raise RuntimeError(f'Service did not become ready: {url}')


def main():
    """Run both local services until Ctrl+C; clean up only processes we created."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--check', action='store_true', help='Start, verify, then stop.')
    args = parser.parse_args()
    children, logs = [], []
    try:
        if sys.platform != 'win32' or sys.maxsize <= 2**32:
            raise RuntimeError('This package requires 64-bit Windows 10/11.')
        for port in (API_PORT, WEB_PORT):
            free_port(port)
        import runpy
        runpy.run_path(str(ROOT/'apply_group_update.py'))['apply_pending'](ROOT)
        log_dir = ROOT / 'data' / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        external_asr_model = env.pop('KNOWGPT_ASR_MODEL', None)
        for name in list(env):
            if name.startswith(('KNOWGPT_', 'PYTHON')) or name in {'NODE_OPTIONS', 'NODE_PATH'}:
                env.pop(name, None)
        asr_model = external_asr_model or str(pick_asr_model())
        env.update(KNOWGPT_DATA_DIR=str(ROOT/'data'), KNOWGPT_ASR_MODEL=asr_model,
                   KNOWGPT_ASR_DEVICE='cpu', HF_HUB_OFFLINE='1', NEXT_TELEMETRY_DISABLED='1',
                   HOSTNAME='127.0.0.1', PORT=str(WEB_PORT), PYTHONDONTWRITEBYTECODE='1',
                   PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
        print(f'ASR model: {asr_model}', flush=True)
        flags = subprocess.CREATE_NO_WINDOW
        for name, command, cwd in [
            ('backend', [str(ROOT/'runtime'/'python'/'python.exe'), '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(API_PORT)], ROOT/'backend'),
            ('frontend', [str(ROOT/'runtime'/'node'/'node.exe'), 'server.js'], ROOT/'web')]:
            log = open(log_dir/f'{name}.log', 'w', encoding='utf-8')
            logs.append(log)
            child = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
            children.append(child)
            url = f'http://127.0.0.1:{API_PORT}/api/health' if name == 'backend' else f'http://127.0.0.1:{WEB_PORT}'
            wait_ready(url, child)
        wait_ready(f'http://127.0.0.1:{WEB_PORT}/api/health', children[1])
        print(f'SpeakLink ready: http://127.0.0.1:{WEB_PORT}', flush=True)
        print('Keep this window open. Press Ctrl+C to stop.', flush=True)
        if args.check:
            return
        if not args.no_browser:
            webbrowser.open(f'http://127.0.0.1:{WEB_PORT}')
        while all(child.poll() is None for child in children):
            time.sleep(.5)
        raise RuntimeError('A service stopped. See data/logs.')
    except KeyboardInterrupt:
        print('Stopping SpeakLink...', flush=True)
    except Exception as error:
        print(f'ERROR: {error}', file=sys.stderr, flush=True)
        return 1
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    child.kill(); child.wait()
        for log in logs:
            log.close()
    return 0


if __name__ == '__main__':
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, signal.default_int_handler)
    sys.exit(main())
