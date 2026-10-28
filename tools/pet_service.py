"""Desktop-pet service owner: reuse healthy services, otherwise own a kill-on-close job.

Never terminates an existing listener. Status is written atomically for the WPF UI.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time


def write_status(path: Path, state: str, message: str = '') -> None:
    """Publish one complete UTF-8 status record without partially read JSON."""
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'state': state, 'message': message}, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def require_free_port(port: int) -> None:
    """Reject occupied ports; never infer process ownership from an HTTP response."""
    with socket.socket() as listener:
        try:
            listener.bind(('127.0.0.1', port))
        except OSError as error:
            raise RuntimeError(f'端口 {port} 已占用。请等待原启动窗口完成启动，或从原窗口退出后重试。桌宠不会关闭已有服务。') from error


def protect_children() -> int:
    """Attach this supervisor to a Windows job; exit kills only its descendants."""
    class Basic(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                    ('flags', wintypes.DWORD), ('min_ws', ctypes.c_size_t),
                    ('max_ws', ctypes.c_size_t), ('active', wintypes.DWORD),
                    ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD),
                    ('scheduling', wintypes.DWORD)]
    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]
    class Extended(ctypes.Structure):
        _fields_ = [('basic', Basic), ('io', IO), ('process_memory', ctypes.c_size_t),
                    ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    api.CreateJobObjectW.restype = wintypes.HANDLE
    api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    api.GetCurrentProcess.restype = wintypes.HANDLE
    handle = api.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = Extended()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not api.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not api.AssignProcessToJobObject(handle, api.GetCurrentProcess()):
        raise ctypes.WinError(ctypes.get_last_error())
    return handle  # Kept open until process exit; handle is not inheritable.


def watch_owner(owner_pid: int) -> None:
    """Exit if the exact parent process dies, including a force-closed WPF window."""
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    handle = api.OpenProcess(0x00100000, False, owner_pid)  # SYNCHRONIZE only
    if not handle:
        raise RuntimeError('桌宠窗口已关闭，取消启动。')

    def wait() -> None:
        if api.WaitForSingleObject(handle, 0xFFFFFFFF) == 0:
            os._exit(0)  # Closes the job handle and all owned services.

    threading.Thread(target=wait, daemon=True).start()


def run(root: Path, status: Path) -> int:
    """Reuse a complete installation, or launch the existing launcher under ownership."""
    spec = importlib.util.spec_from_file_location('knowgpt_launcher', root / 'launcher.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    if launcher.answers_like_backend(18000) and launcher.answers_like_frontend(13000) and launcher.answers_like_backend(13000):
        write_status(status, 'reused', '已连接运行中的 SpeakLink')
        return 0
    require_free_port(18000)
    require_free_port(13000)
    job_handle = protect_children()
    launcher.free_port = require_free_port
    original_wait = launcher.wait_ready

    def patient_wait(url, child, timeout=240):
        """Allow first-run database/model setup without declaring a premature failure."""
        return original_wait(url, child, timeout)

    launcher.wait_ready = patient_wait
    stop = threading.Event()

    def monitor() -> None:
        """Notify the UI once both services and the frontend API proxy are ready."""
        while not stop.wait(1):
            if launcher.answers_like_backend(13000) and launcher.answers_like_frontend(13000):
                write_status(status, 'ready', '速记已准备好')
                return

    threading.Thread(target=monitor, daemon=True).start()
    sys.argv = ['launcher.py', '--no-browser']
    try:
        result = launcher.main()
        write_status(status, 'error', '服务已停止，请查看 data/logs/pet-service.log 后重试。')
        return result or 0
    finally:
        stop.set()
        # The operating system closes job_handle on supervisor exit, including force exit.


if __name__ == '__main__':
    project = Path(__file__).resolve().parent.parent
    state_path = project / 'data' / 'pet-status.json'
    state_path.parent.mkdir(parents=True, exist_ok=True)
    write_status(state_path, 'starting', '正在准备语音速记，请稍候…')
    log_dir = project / 'data' / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / 'pet-service.log').open('w', encoding='utf-8', buffering=1) as log:
        sys.stdout = sys.stderr = log
        try:
            if len(sys.argv) != 2 or int(sys.argv[1]) <= 0:
                raise RuntimeError('请通过桌宠窗口启动此服务。')
            watch_owner(int(sys.argv[1]))
            code = run(project, state_path)
        except Exception as error:
            import traceback
            traceback.print_exc()
            write_status(state_path, 'error', str(error))
            code = 1
        sys.exit(code)
