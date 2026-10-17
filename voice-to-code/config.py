"""Configuration, read from environment variables.

Copy `.env.example` to `.env` and fill it in, or export these in your shell.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class Settings:
    # ---- Twilio ----------------------------------------------------------
    twilio_account_sid: str = _env("TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = _env("TWILIO_AUTH_TOKEN")
    # Preferred for downloading recordings (Twilio requires Basic auth on media URLs).
    twilio_api_key_sid: str = _env("TWILIO_API_KEY_SID")
    twilio_api_key_secret: str = _env("TWILIO_API_KEY_SECRET")
    # A Twilio number you own, in E.164, e.g. +14155550123
    twilio_from_number: str = _env("TWILIO_FROM_NUMBER")
    # The phone you want the system to dial by default (your mobile).
    target_number: str = _env("TARGET_NUMBER")

    # ---- Public URL of this server --------------------------------------
    # Twilio must be able to reach your webhooks. Use ngrok / cloudflared in dev.
    public_base_url: str = _env("PUBLIC_BASE_URL").rstrip("/")

    # ---- Speech to text --------------------------------------------------
    # "openai" (Whisper) or "sarvam" (Saaras, better for Indian languages).
    stt_provider: str = _env("STT_PROVIDER", "openai")
    sarvam_language_code: str = _env("SARVAM_LANGUAGE_CODE", "unknown")
    # "transcribe" keeps the original language; "translate" converts any Indic
    # language to English, which the coding agent follows most reliably.
    sarvam_mode: str = _env("SARVAM_MODE", "translate")

    # ---- Coding agent ----------------------------------------------------
    project_dir: str = os.path.expanduser(_env("PROJECT_DIR", "~/my-project"))
    claude_binary: str = _env("CLAUDE_BINARY", "claude")
    # acceptEdits auto-approves file edits but NOT shell commands.
    agent_permission_mode: str = _env("AGENT_PERMISSION_MODE", "acceptEdits")
    agent_allowed_tools: str = _env(
        "AGENT_ALLOWED_TOOLS", "Read,Edit,Write,MultiEdit,Grep,Glob"
    )
    agent_branch_prefix: str = _env("AGENT_BRANCH_PREFIX", "voice")
    agent_timeout_seconds: int = int(_env("AGENT_TIMEOUT_SECONDS", "900"))

    # ---- Server ----------------------------------------------------------
    port: int = int(_env("PORT", "8000"))
    work_dir: Path = Path(_env("WORK_DIR", "./recordings")).expanduser()
    log_dir: Path = Path(_env("LOG_DIR", "./logs")).expanduser()


settings = Settings()
settings.work_dir.mkdir(parents=True, exist_ok=True)
settings.log_dir.mkdir(parents=True, exist_ok=True)
