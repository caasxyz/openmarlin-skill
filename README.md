# claw-federation-skill

OpenClaw skill for guided platform registration and account linking against
`claw-federation-server`.

Primary entrypoints:

- `SKILL.md` for OpenClaw skill behavior and operator guidance
- `scripts/registration_session.py` for creating, polling, resuming, and
  bootstrapping workspace API keys after registration
- `scripts/platform_request.py` for explicit provider selection, routing hints,
  and authenticated `/invoke` or `/v1/responses` platform requests
- `scripts/payment_recovery.py` for structured 402 recovery guidance and
  authenticated top-up session handling
