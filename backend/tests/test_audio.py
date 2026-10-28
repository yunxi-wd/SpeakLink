"""Audio upload, failed-ASR recovery, silence and timestamp provenance regressions."""
from types import SimpleNamespace
from app.services import asr

def test_audio_retry_preserves_upload(client, monkeypatch):
    """A missing model must leave audio available for retry without a second upload."""
    sid = client.post('/api/sessions', json={'title': 'audio recovery'}).json()['id']
    result = client.post(f'/api/sessions/{sid}/audio', files={'file': ('test.wav', b'RIFF-test', 'audio/wav')})
    assert result.status_code == 200
    path = result.json()['audio_path']
    def fail(*args):
        raise RuntimeError('model unavailable')
    monkeypatch.setattr(asr, 'model', fail)
    assert client.post(f'/api/sessions/{sid}/transcribe').status_code == 503
    snap = client.get(f'/api/sessions/{sid}').json()
    assert snap['session']['audio_path'] == path and snap['segments'] == []
    class Engine:
        """Deterministic ASR adapter for API lifecycle testing only."""
        def transcribe(self, path, **kwargs):
            assert kwargs['vad_filter'] and kwargs['word_timestamps']
            return iter([SimpleNamespace(start=.25, end=2.5, text='嗯，张三参与项目。', avg_logprob=-.1)]), None
    monkeypatch.setattr(asr, 'model', lambda: Engine())
    response = client.post(f'/api/sessions/{sid}/transcribe')
    assert response.status_code == 200, response.text
    segment = response.json()['segments'][0]
    assert segment['start_ms'] == 250 and segment['end_ms'] == 2500
    assert segment['raw_text'] == '嗯，张三参与项目。' and segment['text'] == '张三参与项目。'

def test_silent_audio_not_fabricated(client, monkeypatch):
    """No VAD segments produces an actionable error, not an invented transcription."""
    sid = client.post('/api/sessions', json={}).json()['id']
    client.post(f'/api/sessions/{sid}/audio', files={'file': ('silence.wav', b'RIFF-test', 'audio/wav')})
    monkeypatch.setattr(asr, 'transcribe', lambda *args: [])
    response = client.post(f'/api/sessions/{sid}/transcribe')
    assert response.status_code == 422 and '未检测到语音' in response.json()['detail']
    assert client.get(f'/api/sessions/{sid}').json()['segments'] == []

def test_audio_health_contract(client):
    """Health exposes an explicit engine flag and explanation before recording."""
    result = client.get('/api/health').json()
    assert isinstance(result['asr_installed'], bool)
    assert result['asr_model'] and result['asr_message']
