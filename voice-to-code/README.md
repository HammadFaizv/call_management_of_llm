# voice-to-code

Call a phone number, speak an instruction, hang up — and a coding agent applies
it to your project while you watch the diff appear in VS Code.

```
   you dial  ──►  Twilio  ──►  <Record> your voice
                                    │
                          call ends / you hang up
                                    ▼
                     webhook  /recording-done
                                    │
                    download audio ─► speech-to-text
                                    │
                        transcript (the instruction)
                                    ▼
              git checkout -b voice/...  ─►  claude --print "<instruction>"
                                    │
                         files change on disk
                                    ▼
                     VS Code shows the diff (uncommitted)
```

## What each piece is

| Piece | Choice |
|---|---|
| Telephony | Twilio Programmable Voice |
| Audio capture | TwiML `<Record>` verb (records just your instruction) |
| Speech to text | OpenAI Whisper, or Sarvam Saaras for Indian languages |
| Coding agent | Claude Code CLI, headless (`claude --print`) |
| Server | Python / FastAPI |

## Prerequisites

1. A Twilio account with a voice-capable number.
2. Python 3.10+.
3. Claude Code installed and authenticated (`npm i -g @anthropic-ai/claude-code`,
   then run `claude` once to log in, or set `ANTHROPIC_API_KEY`).
4. A **git repository** you want edited. The agent only ever touches a new
   branch, so pick a project you're happy to experiment on.
5. A public URL for Twilio to reach your webhooks. In development, `ngrok` or
   `cloudflared` is easiest.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit .env
```

Fill in `.env`:

- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`
- `TWILIO_API_KEY_SID` / `TWILIO_API_KEY_SECRET` (preferred for downloading
  recordings; Twilio requires Basic auth on media URLs)
- `TARGET_NUMBER` — the phone it should call (your mobile)
- `PUBLIC_BASE_URL` — your tunnel URL, no trailing slash
- `PROJECT_DIR` — absolute path to the git project
- `OPENAI_API_KEY` (or `STT_PROVIDER=sarvam` + `SARVAM_API_KEY`)

## Run

```bash
# terminal 1 - expose the server
uvicorn server:app --host 0.0.0.0 --port 8000

# terminal 2 - tunnel, and put the https URL in PUBLIC_BASE_URL
ngrok http 8000
```

Then:

```bash
curl -X POST "http://localhost:8000/call"
```

Your phone rings. Say something like *"in the auth module, add a rate limit of
five attempts per minute"*, press `#` or just hang up. The call ends, the
recording is transcribed, and Claude Code makes the edit on a new `voice/...`
branch. Open the project in VS Code — the changes are in Source Control,
uncommitted.

## Test without a phone call

The `/run` endpoint skips Twilio entirely and feeds an instruction straight to
the agent:

```bash
curl -X POST http://localhost:8000/run \
  -H 'Content-Type: application/json' \
  -d '{"text": "add a hello() function to utils.py"}'
```

Use this to check your agent setup before wiring up the telephony side.

## Safety

This lets a phone call modify your code, so the defaults are deliberately
conservative:

- The agent works on a **new git branch** and never commits or pushes. You
  review the diff before anything lands.
- Claude Code runs in `acceptEdits` mode with **no shell tool**
  (`--allowedTools "Read,Edit,Write,MultiEdit,Grep,Glob"`), so it can edit files
  but cannot run arbitrary commands. Loosen this only if you understand the
  consequences.
- Every run is logged to `logs/<call_sid>.json` with the transcript and the
  `git diff --stat` summary.

Do not expose this server to the open internet without authentication, and do
not point `PROJECT_DIR` at anything you cannot afford to have edited.

## Notes and alternatives

- **Indian languages.** Set `STT_PROVIDER=sarvam` and `SARVAM_MODE=translate` to
  have Hindi/Tamil/etc. speech converted to English before it reaches the agent.
  Sarvam's synchronous endpoint is for audio under ~30 seconds; for longer
  instructions use their Batch API.
- **Real-time transcription.** This build records the call and transcribes it
  after hangup, which is the simplest reliable path. For live transcription you
  would stream call audio over a WebSocket (Twilio Media Streams) into a
  streaming STT service instead — more moving parts, but no wait after hangup.
- **No separate STT.** Twilio can transcribe recordings itself
  (`<Record transcribe="true" transcribeCallback="...">`), which removes the
  speech-to-text dependency at the cost of quality.
- **Other agents.** `agent.py` shells out to a CLI. Swapping Claude Code for
  `aider` or a custom script is a change to one function.
