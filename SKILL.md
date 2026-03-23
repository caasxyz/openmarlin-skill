---
name: claw-federation-registration
description: "Guide platform registration, account linking, and explicit provider routing for claw-federation in an OpenClaw-first flow. Use when: a user wants to register, sign in, connect a platform account, or send a platform request to a specific provider with simple routing hints. NOT for: collecting passwords in chat, issuing undocumented server policy overrides, or website-first onboarding."
metadata:
  {
    "openclaw":
      {
        "emoji": "🦞",
        "skillKey": "claw-federation-registration",
        "requires":
          {
            "bins": ["python3"],
            "env": ["CLAW_FEDERATION_SERVER_URL"],
          },
        "primaryEnv": "CLAW_FEDERATION_SERVER_URL",
      },
  }
---

# Claw Federation Registration

Use this skill when a user wants to create, connect, or resume a
`claw-federation` platform account from inside OpenClaw.

## Core Rules

- Keep the flow OpenClaw-led by default.
- Do not collect raw credentials, passwords, magic links, or MFA secrets in chat.
- Prefer the `device` auth flow first because it keeps state management and
  completion polling inside OpenClaw.
- Use `workos_callback` only when the deployment explicitly requires a direct
  browser callback handoff.
- After handoff begins, keep polling or resuming in OpenClaw until the session
  becomes `completed` or `expired`.
- Treat browser use as a narrow identity step, not the main control plane.
- For platform requests, prefer explicit provider selection first.
- Surface only simple routing hints such as `region=ap-sg` or `tier=premium`.
- Do not invent hidden routing labels or pretend to bypass server validation.
- When routing fails, explain the server-side reason in plain language.

## Server Contract

The skill targets these server endpoints:

- `POST /v1/registration/sessions`
- `GET /v1/registration/sessions/:sessionId`
- `POST /v1/registration/sessions/:sessionId/callback`
- `POST /v1/registration/sessions/:sessionId/device/complete`

Completion states exposed by the server:

- `pending_external_auth`
- `completed`
- `expired`

When completed, the session yields:

- `completion.account_id`
- `completion.workspace.workspace_id`
- `completion.workspace.slug`
- `completion.workspace.display_name`
- `completion.provider_identity.provider`
- `completion.provider_identity.provider_subject`
- `completion.provider_identity.primary_email`
- `completion.is_new_account`
- `completion.credential_bootstrap.status`

The current bootstrap status is expected to be
`pending_api_key_issue` until you call the API key bootstrap endpoint.

After registration completes, the skill can continue with:

- `POST /v1/registration/sessions/:sessionId/api-keys`

That endpoint uses the original handoff proof:

- `device_code` for `device` flows
- `callback_state` for `workos_callback` flows

It returns:

- `api_key.key_id`
- `api_key.workspace_id`
- `api_key.status`
- `api_key.created_at`
- `api_key.last_used_at`
- `api_key.label`
- `secret`

## Setup

Required:

```bash
export CLAW_FEDERATION_SERVER_URL="http://127.0.0.1:3000"
```

Optional direct API key override:

```bash
export CLAW_FEDERATION_PLATFORM_API_KEY="claw_wsk_..."
```

After bootstrap, this env var is no longer required if you store the key into
OpenClaw auth profiles.

Optional browser-handoff templates:

```bash
export CLAW_FEDERATION_WORKOS_DEVICE_URL_TEMPLATE="https://platform.example.com/register/device?code={device_code}"
export CLAW_FEDERATION_WORKOS_CALLBACK_URL_TEMPLATE="https://platform.example.com/register?state={callback_state}"
```

Template placeholders:

- `{device_code}`
- `{callback_state}`
- `{registration_session_id}`

Optional request-routing defaults:

```bash
export CLAW_FEDERATION_DEFAULT_PROVIDER_ID="node-a"
export CLAW_FEDERATION_DEFAULT_ROUTING_LABELS='{"region":"ap-sg"}'
```

If no browser template is configured, keep the user in OpenClaw, surface the
device code or callback state, and explain that the deployment-specific WorkOS
entry URL must be supplied by the platform operator.

## Commands

Create a default device-style session:

```bash
python3 scripts/registration_session.py create
```

Create an explicit callback/browser session:

```bash
python3 scripts/registration_session.py create --auth-flow workos_callback
```

Inspect a pending or completed session:

```bash
python3 scripts/registration_session.py status --session-id <session-id>
```

Poll until the session completes or expires:

```bash
python3 scripts/registration_session.py watch --session-id <session-id>
```

Get raw JSON for tool chaining:

```bash
python3 scripts/registration_session.py watch --session-id <session-id> --json
```

Issue the initial workspace API key after completion:

```bash
python3 scripts/registration_session.py issue-api-key --session-id <session-id>
```

Wait for completion and immediately issue the key:

```bash
python3 scripts/registration_session.py bootstrap --session-id <session-id>
```

Wait for completion, issue the key, and store it in OpenClaw auth profiles:

```bash
python3 scripts/registration_session.py bootstrap \
  --session-id <session-id> \
  --store
```

Send an authenticated `/v1/responses` request to an explicitly selected
provider:

```bash
python3 scripts/platform_request.py responses \
  --provider node-a \
  --body-json '{"model":"openai-codex/gpt-5.4","input":"say hello"}'
```

Send a request with simple routing hints:

```bash
python3 scripts/platform_request.py responses \
  --provider node-a \
  --label region=ap-sg \
  --label tier=premium \
  --body-json '{"model":"openai-codex/gpt-5.4","input":"summarize this"}'
```

Invoke a registered remote skill with explicit provider selection:

```bash
python3 scripts/platform_request.py invoke \
  --skill demo.echo \
  --provider node-a \
  --input-json '{"text":"hello"}'
```

## Recommended Playbook

### New Registration

1. Confirm the user wants to register or connect their platform account.
2. Start with `device` flow unless the deployment explicitly says to use
   `workos_callback`.
3. Create the session with
   `python3 scripts/registration_session.py create`.
4. Present only the minimum external-auth instructions:
   - if a device URL is available, open or show it with the device code
   - otherwise show the device code and explain the platform operator must
     provide the verification URL
5. Continue polling with `watch` and keep the conversation in OpenClaw.
6. On completion, issue and store the first workspace API key with
   `python3 scripts/registration_session.py bootstrap --session-id <session-id> --store`
   or `issue-api-key --store` if the session is already completed.
7. Summarize the linked account, workspace context, and that a platform API key
   was bootstrapped and stored for OpenClaw reuse.

### Connect Existing Account

Use the same flow as registration. The server links by
`provider + provider_subject`, so a returning WorkOS identity should resolve to
the same `account_id` and workspace rather than creating a duplicate account.

### Resume A Pending Flow

If the user already has a `registration_session_id`, do not create a new one
first. Resume with:

```bash
python3 scripts/registration_session.py watch --session-id <session-id>
```

If the session is expired, start a fresh session and explain that the prior
handoff timed out.

## Completion Handling

When a session reaches `completed`:

- confirm whether this was a new account or an existing linked account
- summarize the workspace `display_name` and `slug`
- preserve the `account_id` and `workspace_id` for the bootstrap step
- if no key has been issued yet, call the API key bootstrap endpoint with the
  original handoff proof from the session
- treat the returned `secret` as sensitive and do not paste it back into
  version-controlled files

## Credential Handling

The returned `secret` is the steady-state platform credential for OpenClaw.

- prefer OpenClaw auth profiles over plain repo files or ordinary config
- store the key in `~/.openclaw/agents/<agentId>/agent/auth-profiles.json`
  using the default profile `claw-federation-platform:default`
- after storing with `--store`, later `platform_request.py` calls can reuse the
  key automatically without re-exporting it
- do not write the key into ordinary `openclaw.json` fields
- if you only need to hand it off manually, use process env or operator-managed
  secret storage rather than chat history when possible

## Provider Routing UX

The platform routing model is explicit-provider-first.

Preferred user-facing controls:

- explicit `provider_id` when the user knows the target node
- optional simple labels expressed as `key=value`
- env-based defaults when the same provider or routing hint should persist
  across repeated requests

Good examples:

- "send this to provider `node-a`"
- "use `node-a` in `region=ap-sg`"
- "default to provider `node-b` for this workspace session"

Avoid exposing low-level policy internals. Keep the UX to:

- provider choice
- a small number of understandable labels
- clear explanations when the server rejects the route

## Routing Failure Guidance

Translate common server responses into plain language:

- `provider_unavailable`: the selected provider is not currently connected
- `provider_label_mismatch`: the provider does not satisfy the requested routing
  hints
- `skill_not_available_on_provider`: that provider does not expose the requested
  skill
- `skill_not_available`: no connected provider currently exposes that skill
- `llm_api_not_available`: the provider is connected but does not forward the
  `responses` API
- `llm_model_not_allowed`: the requested model is outside the provider allowlist
- `invalid_routing_labels`: the label hints were not valid JSON or `key=value`
  pairs

When these happen, keep the explanation concrete:

- restate the provider and labels you actually sent
- say whether the user should retry with a different provider, different labels,
  or no labels
