"""Test queued update activation and rollback using disposable directories only."""
from pathlib import Path
import hashlib,json,runpy,tempfile,unittest,os
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
apply_pending=runpy.run_path(str(ROOT/'apply_group_update.py'))['apply_pending']

class UpdateTests(unittest.TestCase):
    """Updating must preserve recording/ASR files and recover from interrupted activation."""
    def fixture(self):
        """Build a tiny old installation and a checksum-protected new payload."""
        root=Path(tempfile.mkdtemp(prefix='knowgpt-update-test-'))
        originals={'backend/app/services/example.py':'old code','web/server.js':'old server','web/.next/BUILD_ID':'old build','data/recording.txt':'user recording','backend/app/services/asr.py':'user ASR'}
        for name,text in originals.items():
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
        files={}
        for name,text in {'backend/app/services/example.py':'new code','web/server.js':'new server','web/.next/BUILD_ID':'new build'}.items():
            p=root/'.group-update'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text);files[name]=hashlib.sha256(p.read_bytes()).hexdigest()
        (root/'.group-update/manifest.json').write_text(json.dumps({'files':files}))
        return root

    def test_activation_and_idempotence(self):
        root=self.fixture();self.assertTrue(apply_pending(root));self.assertFalse(apply_pending(root))
        self.assertEqual((root/'web/.next/BUILD_ID').read_text(),'new build')
        self.assertEqual((root/'data/recording.txt').read_text(),'user recording')
        self.assertEqual((root/'backend/app/services/asr.py').read_text(),'user ASR')
        self.assertTrue(list((root/'upgrade-backups').glob('groups-*/web/.next/BUILD_ID')))

    def test_checksum_failure_does_not_modify_installation(self):
        root=self.fixture();(root/'.group-update/web/server.js').write_text('corrupted')
        with self.assertRaises(RuntimeError):apply_pending(root)
        self.assertEqual((root/'web/server.js').read_text(),'old server')

    def test_activation_error_rolls_back(self):
        root=self.fixture();replace=os.replace
        def fail(source,target):
            if Path(source)==root/'.group-update/web/.next':raise OSError('simulated locked frontend')
            return replace(source,target)
        with patch('os.replace',side_effect=fail):
            with self.assertRaises(OSError):apply_pending(root)
        self.assertEqual((root/'web/.next/BUILD_ID').read_text(),'old build')
        self.assertEqual((root/'web/server.js').read_text(),'old server')
        self.assertEqual((root/'backend/app/services/example.py').read_text(),'old code')

    def test_forbidden_path_rejected(self):
        root=self.fixture();manifest=root/'.group-update/manifest.json';payload=json.loads(manifest.read_text());payload['files']['data/recording.txt']='x';manifest.write_text(json.dumps(payload))
        with self.assertRaises(RuntimeError):apply_pending(root)
        self.assertEqual((root/'data/recording.txt').read_text(),'user recording')

    def test_second_backend_only_update_preserves_ui(self):
        root=self.fixture();apply_pending(root)
        source=root/'.group-update/backend/app/services/example.py';source.write_text('second code')
        (root/'.group-update/manifest.json').write_text(json.dumps({'files':{'backend/app/services/example.py':hashlib.sha256(source.read_bytes()).hexdigest()}}))
        self.assertTrue(apply_pending(root))
        self.assertEqual((root/'backend/app/services/example.py').read_text(),'second code')
        self.assertEqual((root/'web/.next/BUILD_ID').read_text(),'new build')

if __name__=='__main__':unittest.main(verbosity=2)
