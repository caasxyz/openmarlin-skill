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
