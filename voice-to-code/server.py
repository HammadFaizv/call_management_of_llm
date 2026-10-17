"""voice-to-code: dial a number, speak an instruction, hang up, and a coding
agent applies it to your project.

Flow:
    POST /call             Twilio dials TARGET_NUMBER
    POST /voice            TwiML: greet, then <Record> the instruction
    POST /recording-done   Twilio reports the finished recording -> queue job
    (background)           download audio -> transcribe -> run Claude Code -> log
    POST /run              manual trigger, for testing without a phone call
    GET  /health           liveness check
"""

import json
import logging
import time
from pathlib import Path

import requests
import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

from agent import run_agent
from config import settings
from transcribe import transcribe

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("voice-to-code")

app = FastAPI(title="voice-to-code")
twilio_client = Client(settings.twilio_account_sid, settings.twilio_auth_token)


# --------------------------------------------------------------------------
# Triggering the call
# --------------------------------------------------------------------------
@app.post("/call")
def start_call(to: str | None = None):
    """Ask Twilio to dial a number. `?to=+91...` overrides TARGET_NUMBER."""
    target = (to or settings.target_number).strip()
    if not target:
        raise HTTPException(400, "No target number. Set TARGET_NUMBER or pass ?to=")
    if not settings.public_base_url:
        raise HTTPException(400, "PUBLIC_BASE_URL is not set (use ngrok in dev)")

    call = twilio_client.calls.create(
        to=target,
        from_=settings.twilio_from_number,
        url=f"{settings.public_base_url}/voice",
    )
    log.info("dialing %s (call %s)", target, call.sid)
    return {"call_sid": call.sid, "to": target}


# --------------------------------------------------------------------------
# What happens when the call connects
# --------------------------------------------------------------------------
@app.post("/voice")
async def voice():
    """TwiML served the moment the call connects."""
    resp = VoiceResponse()
    resp.say(
        "Hi. Tell me what you want changed in the project. "
        "Press hash when you are done, or just hang up."
    )
    resp.record(
        action=f"{settings.public_base_url}/recording-done",
        method="POST",
        finish_on_key="#",
        max_length=600,
        play_beep=True,
        trim="trim-silence",
    )
    # NOTE: any TwiML after <Record> is unreachable - the call is continued by
    # the TwiML we return from the action URL (/recording-done).
    return PlainTextResponse(str(resp), media_type="application/xml")


@app.post("/recording-done")
async def recording_done(request: Request, background: BackgroundTasks):
    """Fired when recording ends - including when the caller hangs up.

    Twilio sends RecordingUrl, RecordingDuration and Digits ('hangup' if the
    caller hung up). We queue the heavy work and answer the call immediately.
    """
    form = await request.form()
    recording_url = form.get("RecordingUrl")
    call_sid = form.get("CallSid", "unknown")
    log.info(
        "recording finished call=%s duration=%ss digits=%s",
        call_sid,
        form.get("RecordingDuration", "?"),
        form.get("Digits", ""),
    )

    if recording_url:
        background.add_task(process_recording, call_sid, recording_url)
    else:
        log.warning("no RecordingUrl in callback for call %s", call_sid)

    resp = VoiceResponse()
    resp.say("Got it. Starting on that now. Goodbye.")
    resp.hangup()
    return PlainTextResponse(str(resp), media_type="application/xml")


# --------------------------------------------------------------------------
# Manual trigger (no phone needed) - handy while developing
# --------------------------------------------------------------------------
@app.post("/run")
async def run_manual(payload: dict, background: BackgroundTasks):
    text = (payload or {}).get("text", "").strip()
    if not text:
        raise HTTPException(400, "Body must be JSON like {\"text\": \"...\"}")
    background.add_task(process_instruction, "manual", text)
    return {"status": "queued", "instruction": text}


@app.get("/health")
def health():
    return {"ok": True, "project_dir": settings.project_dir}


# --------------------------------------------------------------------------
# The pipeline
# --------------------------------------------------------------------------
def process_recording(call_sid: str, recording_url: str) -> None:
    try:
        audio = download_recording(recording_url, call_sid)
        text = transcribe(audio)
        log.info("transcript for %s: %r", call_sid, text)
        if not text:
            log.warning("empty transcript for %s - nothing to do", call_sid)
            return
        process_instruction(call_sid, text)
    except Exception:
        log.exception("pipeline failed for call %s", call_sid)


def process_instruction(call_sid: str, instruction: str) -> None:
    try:
        result = run_agent(instruction)
        log.info(
            "agent done call=%s branch=%s rc=%s\n%s",
            call_sid,
            result["branch"],
            result["returncode"],
            result["diff_stat"] or "(no changes)",
        )
        write_log(call_sid, instruction, result)
    except Exception:
        log.exception("agent run failed for %s", call_sid)


def download_recording(recording_url: str, call_sid: str) -> Path:
    """Download the call audio as MP3.

    Twilio's media URLs need HTTP Basic auth, and the file can lag the callback
    by a second or two, so we retry a few times with backoff.
    """
    mp3_url = recording_url + ".mp3"
    user = settings.twilio_api_key_sid or settings.twilio_account_sid
    password = settings.twilio_api_key_secret or settings.twilio_auth_token
    dest = settings.work_dir / f"{call_sid}.mp3"

    last_status = None
    for attempt in range(1, 6):
        resp = requests.get(mp3_url, auth=(user, password), timeout=60)
        if resp.status_code == 200 and resp.content:
            dest.write_bytes(resp.content)
            log.info("saved recording to %s (%d bytes)", dest, len(resp.content))
            return dest
        last_status = resp.status_code
        log.info("recording not ready (%s), retry %d/5", resp.status_code, attempt)
        time.sleep(2 * attempt)
    raise RuntimeError(f"could not download recording (last status {last_status})")


def write_log(call_sid: str, instruction: str, result: dict) -> None:
    record = {"call_sid": call_sid, "instruction": instruction, **result}
    path = settings.log_dir / f"{call_sid}.json"
    path.write_text(json.dumps(record, indent=2))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
