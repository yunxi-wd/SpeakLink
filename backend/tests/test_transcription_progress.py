"""Real HTTP lifecycle tests with a controllable ASR generator; no model quality claims."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from app.services import asr, transcription_progress as progress


def test_progress_observable_during_asr_and_duplicate_rejected(client, monkeypatch):
    """Poll completed segment coverage while inference is blocked on its next segment."""
    sid = client.post('/api/sessions', json={'title': 'progress test'}).json()['id']
    client.post(f'/api/sessions/{sid}/audio', files={'file': ('test.wav', b'RIFF-test', 'audio/wav')})
    waiting, release = Event(), Event()

    def recognize(path, **options):
        assert options['condition_on_previous_text'] is False
        assert options['vad_filter'] and options['word_timestamps']
        def segments():
            yield SimpleNamespace(start=0, end=3, text='人工智能参与任务。', avg_logprob=-.1)
            waiting.set()
            assert release.wait(10)
            yield SimpleNamespace(start=3, end=10, text='任务包括语言理解。', avg_logprob=-.1)
        return segments(), SimpleNamespace(duration=10)

    monkeypatch.setattr(asr, 'model', lambda: SimpleNamespace(transcribe=recognize))
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(client.post, f'/api/sessions/{sid}/transcribe')
        try:
            assert waiting.wait(5)
            value = client.get(f'/api/sessions/{sid}/transcription-progress').json()
            assert value['stage'] == 'recognizing'
            assert value['processed_ms'] == 3000 and value['duration_ms'] == 10000
            assert value['segments_count'] == 1 and 0 < value['percent'] < 100
            assert client.post(f'/api/sessions/{sid}/transcribe').status_code == 409
        finally:
            release.set()
        assert future.result(10).status_code == 200
    value = client.get(f'/api/sessions/{sid}/transcription-progress').json()
    assert value['stage'] == 'completed' and value['percent'] == 100
    assert len(client.get(f'/api/sessions/{sid}').json()['segments']) == 2


def test_progress_failure_and_retry(client, monkeypatch):
    """Missing models are reported as failures, with saved audio and a released lease."""
    sid = client.post('/api/sessions', json={}).json()['id']
    client.post(f'/api/sessions/{sid}/audio', files={'file': ('test.wav', b'RIFF-test', 'audio/wav')})
    def missing():
        raise RuntimeError('model unavailable')
    monkeypatch.setattr(asr, 'model', missing)
    assert client.post(f'/api/sessions/{sid}/transcribe').status_code == 503
    assert client.get(f'/api/sessions/{sid}/transcription-progress').json()['stage'] == 'failed'
    assert progress.begin(sid)
    progress.fail(sid)
    assert client.get(f'/api/sessions/{sid}').json()['session']['audio_path']


def test_unknown_duration_is_indeterminate():
    """Do not fabricate percentage before a real audio duration is available."""
    sid = 'telemetry-unit'
    assert progress.begin(sid)
    assert progress.read(sid).percent is None
    progress.update(sid, 'recognizing', 10, 0, 1)
    assert progress.read(sid).percent is None
    progress.fail(sid)
    assert progress.begin(sid)
    assert progress.read(sid).processed_ms == 0
    progress.fail(sid)


def test_progress_does_not_expose_other_session(client):
    """Progress is session-scoped and checks the database before returning status."""
    assert client.get('/api/sessions/missing/transcription-progress').status_code == 404
