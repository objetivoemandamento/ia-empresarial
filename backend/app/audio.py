from __future__ import annotations
from pathlib import Path
from tempfile import NamedTemporaryFile
from .config import Settings

ALLOWED_LANGUAGES = {"pt", "en", "zh", "es", "hi"}
PROVIDER_LANGUAGE_HINTS = {
    "pt": "Portuguese", "en": "English", "zh": "Chinese",
    "es": "Spanish", "hi": "Hindi",
}

class AudioUnavailable(RuntimeError):
    pass

async def transcribe_audio(data: bytes, filename: str, language: str, settings: Settings) -> str:
    if language not in ALLOWED_LANGUAGES:
        raise ValueError("Unsupported language")
    if not settings.openai_api_key:
        raise AudioUnavailable("Server transcription is not configured; use browser speech recognition or configure OPENAI_API_KEY.")
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise AudioUnavailable("OpenAI SDK is not installed; install backend requirements to enable server transcription.") from exc
    suffix = Path(filename).suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a", ".webm", ".mp4", ".mpeg", ".mpga", ".ogg", ".flac"}:
        suffix = ".webm"
    temp_path: str | None = None
    try:
        with NamedTemporaryFile(prefix="audio-", suffix=suffix, delete=False) as temp:
            temp.write(data)
            temp_path = temp.name
        client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=90.0, max_retries=2)
        with open(temp_path, "rb") as audio:
            result = await client.audio.transcriptions.create(
                model=settings.transcription_model,
                file=audio,
                language=language,
            )
        text = getattr(result, "text", "")
        if not text:
            raise AudioUnavailable("Transcription provider returned no text")
        return text
    except Exception as exc:
        if isinstance(exc, (AudioUnavailable, ValueError)):
            raise
        raise AudioUnavailable(f"Transcription failed: {exc.__class__.__name__}") from exc
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)
