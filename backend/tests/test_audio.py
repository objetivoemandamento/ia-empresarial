from pathlib import Path
from types import SimpleNamespace

import pytest

from app.audio import AudioUnavailable, transcribe_audio
from app.config import Settings


@pytest.mark.asyncio
async def test_transcribe_audio_success_and_temp_file_cleanup(monkeypatch):
    captured = {}

    class FakeTranscriptions:
        async def create(self, **kwargs):
            captured["path"] = kwargs["file"].name
            assert Path(captured["path"]).exists()
            assert kwargs["language"] == "pt"
            return SimpleNamespace(text="Áudio transcrito")

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            captured["timeout"] = kwargs["timeout"]
            self.audio = SimpleNamespace(transcriptions=FakeTranscriptions())

    monkeypatch.setattr("openai.AsyncOpenAI", FakeAsyncOpenAI)
    result = await transcribe_audio(b"audio-bytes", "voice.wav", "pt", Settings(openai_api_key="test-key"))
    assert result == "Áudio transcrito"
    assert captured["timeout"] == 90.0
    assert not Path(captured["path"]).exists()


@pytest.mark.asyncio
async def test_transcribe_audio_rejects_unsupported_language():
    with pytest.raises(ValueError, match="Unsupported language"):
        await transcribe_audio(b"audio", "voice.webm", "xx", Settings(openai_api_key="test-key"))


@pytest.mark.asyncio
async def test_transcribe_audio_requires_api_key():
    with pytest.raises(AudioUnavailable, match="not configured"):
        await transcribe_audio(b"audio", "voice.webm", "pt", Settings(openai_api_key=""))


@pytest.mark.asyncio
async def test_transcribe_audio_empty_result_is_a_controlled_error(monkeypatch):
    captured = {}

    class FakeTranscriptions:
        async def create(self, **kwargs):
            captured["path"] = kwargs["file"].name
            return SimpleNamespace(text="")

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.audio = SimpleNamespace(transcriptions=FakeTranscriptions())

    monkeypatch.setattr("openai.AsyncOpenAI", FakeAsyncOpenAI)
    with pytest.raises(AudioUnavailable, match="no text"):
        await transcribe_audio(b"audio", "voice.unknown", "en", Settings(openai_api_key="test-key"))
    assert not Path(captured["path"]).exists()


@pytest.mark.asyncio
async def test_transcribe_audio_sanitizes_provider_errors(monkeypatch):
    captured = {}

    class FakeTranscriptions:
        async def create(self, **kwargs):
            captured["path"] = kwargs["file"].name
            raise RuntimeError("sensitive provider detail")

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs):
            self.audio = SimpleNamespace(transcriptions=FakeTranscriptions())

    monkeypatch.setattr("openai.AsyncOpenAI", FakeAsyncOpenAI)
    with pytest.raises(AudioUnavailable, match="Transcription failed: RuntimeError") as err:
        await transcribe_audio(b"audio", "voice.webm", "pt", Settings(openai_api_key="test-key"))
    assert "sensitive provider detail" not in str(err.value)
    assert not Path(captured["path"]).exists()
