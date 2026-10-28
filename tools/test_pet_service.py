"""Regression checks for reuse, port safety, status, and Windows descendant cleanup."""
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

MODULE = Path(__file__).with_name('pet_service.py')
spec = importlib.util.spec_from_file_location('pet_service', MODULE)
pet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pet)


class PetTests(unittest.TestCase):
    """Do not touch live application services or their ports."""

    def test_atomic_status(self):
        """Unicode status can be read and replaced without stale temporary files."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'status.json'
            pet.write_status(path, 'starting', '正在启动')
            pet.write_status(path, 'ready', '已完成')
            self.assertEqual(json.loads(path.read_text(encoding='utf8'))['message'], '已完成')
            self.assertFalse(path.with_suffix('.tmp').exists())

    def test_occupied_port_is_not_killed(self):
        """An unrelated listener remains available after rejection."""
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); listener.listen()
            port = listener.getsockname()[1]
            with self.assertRaises(RuntimeError):
                pet.require_free_port(port)
            with socket.create_connection(('127.0.0.1', port), timeout=1):
                pass

    def test_free_port(self):
        """A free port passes the read-only availability guard."""
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
        pet.require_free_port(port)

    def test_reuse_does_not_create_job_or_start_launcher(self):
        """Complete existing service health must bypass startup and process ownership."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'launcher.py').write_text('def answers_like_backend(p): return True\ndef answers_like_frontend(p): return True\ndef main(): raise AssertionError("must not start")\n')
            with patch.object(pet, 'protect_children', side_effect=AssertionError('must not own')):
                self.assertEqual(pet.run(root, root / 'state.json'), 0)
            self.assertEqual(json.loads((root / 'state.json').read_text(encoding='utf8'))['state'], 'reused')

    @unittest.skipUnless(sys.platform == 'win32', 'Windows Job Object test')
    def test_force_exit_cleans_owned_child(self):
        """A supervisor force-exit releases the job and stops its known child PID."""
        self.check_descendant_cleanup(False)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows parent handle test')
    def test_pet_owner_death_cleans_supervisor_and_child(self):
        """Closing the owning GUI also shuts down supervisor and descendant services."""
        self.check_descendant_cleanup(True)

    def check_descendant_cleanup(self, watch_owner):
        """Exercise real Windows process handles without inspecting unrelated processes."""
        import ctypes
        from ctypes import wintypes
        owner = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(90)']) if watch_owner else None
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / 'pid.txt'
            code = f'''import importlib.util, subprocess, sys, time
s=importlib.util.spec_from_file_location('pet', {str(MODULE)!r}); p=importlib.util.module_from_spec(s); s.loader.exec_module(p)
job=p.protect_children()
{f'p.watch_owner({owner.pid})' if owner else ''}
c=subprocess.Popen([sys.executable,'-c','import time; time.sleep(90)'])
open({str(marker)!r},'w').write(str(c.pid))
time.sleep(90)
'''
            supervisor = subprocess.Popen([sys.executable, '-c', code])
            handle = None
            try:
                deadline = time.monotonic()+10
                while not marker.exists() and time.monotonic()<deadline:
                    time.sleep(.1)
                self.assertTrue(marker.exists())
                api = ctypes.WinDLL('kernel32', use_last_error=True)
                api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
                api.OpenProcess.restype=wintypes.HANDLE
                api.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
                api.CloseHandle.argtypes=[wintypes.HANDLE]
                handle=api.OpenProcess(0x100000,False,int(marker.read_text()))
                self.assertTrue(handle)
                if owner:
                    owner.kill(); owner.wait(timeout=5)
                    supervisor.wait(timeout=5)
                else:
                    supervisor.kill(); supervisor.wait(timeout=5)
                self.assertEqual(api.WaitForSingleObject(handle,5000),0)
            finally:
                if supervisor.poll() is None: supervisor.kill(); supervisor.wait()
                if owner and owner.poll() is None: owner.kill(); owner.wait()
                if handle: api.CloseHandle(handle)


if __name__ == '__main__':
    unittest.main(verbosity=2)
