"""Speech to text: turn a downloaded call recording into an instruction."""

import os

import requests

from config import settings


def transcribe(audio_path: str) -> str:
    """Return the transcript of `audio_path` using the configured provider."""
    if settings.stt_provider == "openai":
        return _openai(audio_path)
    if settings.stt_provider == "sarvam":
        return _sarvam(audio_path)
    raise ValueError(f"Unknown STT_PROVIDER: {settings.stt_provider!r}")


def _openai(audio_path: str) -> str:
    """OpenAI Whisper. Reads OPENAI_API_KEY from the environment."""
    from openai import OpenAI

    client = OpenAI()
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model=os.environ.get("OPENAI_STT_MODEL", "whisper-1"),
            file=f,
        )
    return (getattr(result, "text", "") or "").strip()


def _sarvam(audio_path: str) -> str:
    """Sarvam Saaras.

    NOTE: the synchronous REST endpoint is for audio under ~30 seconds. If your
    instructions run longer, use Sarvam's Batch API instead of this call.
    mode="translate" turns any supported Indic language into English.
    """
    api_key = os.environ["SARVAM_API_KEY"]
    with open(audio_path, "rb") as f:
        resp = requests.post(
            "https://api.sarvam.ai/speech-to-text",
            headers={"api-subscription-key": api_key},
            files={"file": f},
            data={
                "model": os.environ.get("SARVAM_STT_MODEL", "saaras:v3"),
                "mode": settings.sarvam_mode,
                "language_code": settings.sarvam_language_code,
            },
            timeout=120,
        )
    resp.raise_for_status()
    return (resp.json().get("transcript") or "").strip()
