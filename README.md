# claw-federation-skill

OpenClaw skill for guided platform access and billing workflows against
`claw-federation-server`.

This repo covers the OpenClaw-first UX for:

- registration and account linking
- platform API key bootstrap and auth-profile storage
- explicit provider selection and routing hints
- structured `402 Payment Required` recovery
- guided top-up and last-known balance management

Primary entrypoints:

- `SKILL.md` for OpenClaw skill behavior and operator guidance
- `scripts/registration_session.py` for creating, polling, resuming, and
  bootstrapping workspace API keys after registration
- `scripts/platform_request.py` for explicit provider selection, routing hints,
  and authenticated `/invoke` or `/v1/responses` platform requests
- `scripts/payment_recovery.py` for structured 402 recovery guidance and
  authenticated top-up session handling, local balance snapshots, and tracked
  top-up history

Internal helpers:

- `scripts/openclaw_platform_auth.py` for OpenClaw auth-profile storage
- `scripts/openclaw_billing_state.py` for local billing-state persistence

## Installation

### Option 1: Use the repo directly

Clone the repo anywhere and use the skill in place:

```bash
git clone https://github.com/caasxyz/claw-federation-skill.git
cd claw-federation-skill
export CLAW_FEDERATION_SERVER_URL="http://127.0.0.1:3000"
```

This is the simplest path for development or local testing.

### Option 2: Install as a local OpenClaw skill

Copy the repo contents into your local skills directory so OpenClaw can load it
as a standard installed skill:

```bash
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
mkdir -p "$CODEX_HOME/skills/claw-federation"
rsync -a --delete \
  --exclude '.git' \
  /path/to/claw-federation-skill/ \
  "$CODEX_HOME/skills/claw-federation/"
```

After install, the main entrypoint should be:

```text
$CODEX_HOME/skills/claw-federation/SKILL.md
```

The helper scripts remain available relative to that installed skill directory:

```text
$CODEX_HOME/skills/claw-federation/scripts/registration_session.py
$CODEX_HOME/skills/claw-federation/scripts/platform_request.py
$CODEX_HOME/skills/claw-federation/scripts/payment_recovery.py
```

## Requirements

- `python3`
- `CLAW_FEDERATION_SERVER_URL`

Optional but commonly useful:

- `CLAW_FEDERATION_PLATFORM_API_KEY`
- `CLAW_FEDERATION_DEFAULT_PROVIDER_ID`
- `CLAW_FEDERATION_DEFAULT_ROUTING_LABELS`
- `CLAW_FEDERATION_WORKOS_DEVICE_URL_TEMPLATE`
- `CLAW_FEDERATION_WORKOS_CALLBACK_URL_TEMPLATE`

These values do not have to come from a shell `export`. The helper scripts now
resolve them in this order:

1. process environment
2. persisted OpenClaw skill config in `~/.openclaw/openclaw.json`

The persisted OpenClaw config path is:

```text
skills.entries["claw-federation-registration"].env
```

So OpenClaw can remember values such as:

```json
{
  "skills": {
    "entries": {
      "claw-federation-registration": {
        "env": {
          "CLAW_FEDERATION_SERVER_URL": "http://127.0.0.1:3000",
          "CLAW_FEDERATION_DEFAULT_PROVIDER_ID": "node-a",
          "CLAW_FEDERATION_DEFAULT_ROUTING_LABELS": "{\"region\":\"ap-sg\"}"
        }
      }
    }
  }
}
```

In other words, users do not need to hand-edit config files if OpenClaw is
writing skill config through its normal settings or `skills.update` flow.

## First Run

Once installed, common entrypoints are:

```bash
python3 scripts/registration_session.py create
python3 scripts/platform_request.py responses --provider node-a --body-json '{"model":"openai-codex/gpt-5.4","input":"hello"}'
python3 scripts/payment_recovery.py explain-402 --response-file /path/to/402.json
```

For full behavior and flow guidance, use:

- `SKILL.md`
