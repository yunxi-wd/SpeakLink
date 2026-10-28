"""Apply a verified local group-graph update before services start, with rollback."""
from pathlib import Path
import datetime,hashlib,json,os,shutil

def apply_pending(root: Path) -> bool:
    """Verify payload, back up old code, activate compiled UI and preserve recordings."""
    root=root.resolve();pending=root/'.group-update';manifest=pending/'manifest.json'
    if not manifest.exists():return False
    files=json.loads(manifest.read_text(encoding='utf-8'))['files']
    for name,digest in files.items():
        target=(root/name).resolve();source=(pending/name).resolve()
        if not target.is_relative_to(root) or not source.is_relative_to(pending.resolve()) or not name.startswith(('backend/app/','configs/prompts/','web/','tools/','组间关系')):
            raise RuntimeError('Group update contains an invalid path')
        if Path(name).name in {'asr.py','launcher.py','START.cmd','default.yaml'}:raise RuntimeError('Group update may not replace ASR or startup settings')
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:raise RuntimeError('Group update file checksum failed: '+name)
    backup=root/'upgrade-backups'/('groups-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(parents=True)
    written=[];swapped=False;new_next=root/'web/.next';old_next=backup/'web/.next';had_next=new_next.exists()
    update_ui=any(name.startswith('web/.next/') for name in files)
    try:
        for name in files:
            if name.startswith('web/.next/'):continue
            target=root/name;prior=backup/name
            if target.exists():prior.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,prior)
            target.parent.mkdir(parents=True,exist_ok=True)
            written.append((target,prior))
            temporary=target.with_name(target.name+'.group-update.tmp');shutil.copy2(pending/name,temporary);os.replace(temporary,target)
        if update_ui:
            old_next.parent.mkdir(parents=True,exist_ok=True)
            if had_next:os.replace(new_next,old_next)
            try:os.replace(pending/'web/.next',new_next);swapped=True
            except Exception:
                if had_next:os.replace(old_next,new_next)
                raise
        (backup/'installed.json').write_text(json.dumps({'files':files,'recordings_unchanged':True},ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception:
        for target,prior in reversed(written):
            if prior.exists():shutil.copy2(prior,target)
            else:target.unlink(missing_ok=True)
        if swapped:
            # Move the failed UI into the backup rather than recursively deleting it.
            os.replace(new_next,backup/'failed-new-ui')
            if had_next:os.replace(old_next,new_next)
        raise
    os.replace(manifest,pending/'applied-manifest.json')
    status=root/'group-update-ready.json'
    if status.exists():
        try:
            state=json.loads(status.read_text(encoding='utf-8'));state.update(pending=False,applied_backup=str(backup))
            status.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        except (OSError,ValueError):pass
    print('Group relationships update applied. Backup: '+str(backup),flush=True)
    return True
