---
name: openmarlin
description: "Use OpenMarlin from OpenClaw for registration, account linking, exact-model execution requests, remote skill invocation, and billing recovery. Use when: a user wants to register or sign in, use OpenMarlin to answer a question or perform a task, or send a native execution request with automatic routing, an explicit provider override, or simple routing hints. Trigger on natural requests like 'use openmarlin to ...', 'ask openmarlin ...', '用 openmarlin ...', or '用 openmarlin 查一下 ...'. NOT for: collecting passwords in chat, issuing undocumented server policy overrides, or website-first onboarding."
---

# OpenMarlin

Use this skill when a user wants to use OpenMarlin from inside OpenClaw,
whether that means first-time registration or an already-configured execution
or invoke flow.

For new users, the normal first step is still registration and API key
bootstrap before trying the first execution request.

Natural-language triggers that should activate this skill include:

- "use openmarlin to answer this"
- "ask openmarlin to summarize this page"
- "use openmarlin to find today's USD/CNY exchange rate"
- "用 openmarlin 查一下今天美元对人民币的汇率"
- "用 openmarlin 执行这个任务"
- "用 openmarlin 调一下这个远端 skill"

## How To Route Requests

When a user explicitly asks to use OpenMarlin, activate this skill first and
then route the request:

- Requests like "use openmarlin to answer this", "ask openmarlin ...", or
  "用 openmarlin 查一下 ..." should be treated as OpenMarlin execution intent,
  not generic chat.
- For normal tasks such as answering, searching, summarizing, extracting, or
  translating, prefer the execution path.
- If the user explicitly asks to call a named remote skill, prefer `/invoke`.
- If the user explicitly provides an execution payload, an exact model ref, or
  asks for a native execution request, prefer `/v1/executions`.
- Do not reject activation just because the user did not supply `provider_id`,
  labels, or an exact model ref in the first sentence. Activate the skill,
  then guide the missing execution details.
- For platform execution requests, prefer server-side automatic routing by
  default.
- Use explicit provider selection only when the user really wants a specific
  node.
- When using explicit `provider_id` together with an exact `model` for
  `/v1/executions`, first confirm from `python3 scripts/platform_request.py models`
  that the provider advertises that same exact model ref.
- Surface only simple routing hints such as `region=ap-sg` or `tier=premium`.
- Do not invent hidden routing labels or pretend to bypass server validation.

## Quick Summary

OpenMarlin lets OpenClaw users register an account, bootstrap a workspace API
key, discover available models, send routed execution requests, and recover
from prepaid billing failures without leaving the OpenClaw-led flow except for
required browser handoff steps.

Official links:

- Skill repo: [https://github.com/caasxyz/openmarlin-skill](https://github.com/caasxyz/openmarlin-skill)
- Server repo: [https://github.com/caasxyz/openmarlin-server](https://github.com/caasxyz/openmarlin-server)

## Installation

This skill is distributed as a directory, not as a standalone Markdown file.
When installing from a raw URL or a git checkout, install the whole skill
directory instead of copying only `SKILL.md`.

Requirements and install hints:

- `python3` must be available in `PATH`
- `OPENMARLIN_SERVER_URL` defaults to `https://api.openmarlin.ai`
- use the bare API origin for `OPENMARLIN_SERVER_URL`, not a value ending in `/v1`
- if you install manually, copy both `SKILL.md` and `scripts/*.py`
- if your environment supports installer hints, use your normal Python 3 install path for this workspace

Required files:

- `SKILL.md`
- `scripts/registration_session.py`
- `scripts/platform_request.py`
- `scripts/billing.py`
- `scripts/openclaw_billing_state.py`
- `scripts/openclaw_platform_auth.py`
- `scripts/openclaw_skill_config.py`

If `SKILL.md` is present without the sibling `scripts/` files, commands in this
skill will fail with missing-file errors on first use.

## After Install

Tell the user the next step plainly instead of assuming they know the flow.

Recommended first actions:

1. Confirm the configured `OPENMARLIN_SERVER_URL`.
2. Start registration with `python3 scripts/registration_session.py create`.
3. Resume or poll with `watch` until the registration session completes.
4. Bootstrap and store the first workspace API key with `bootstrap --store`.
5. Call `python3 scripts/platform_request.py models` so the user can see valid model ids before picking one.
6. Send the first execution request or invoke call.

After registration completes, the next thing the user usually needs is one of:

- bootstrap and store the first workspace API key
- list available models
- send a first routed execution request
- recover from a `402 Payment Required` response

## What You Can Do Now

- Register a new OpenMarlin account or connect an existing one.
- Bootstrap and store a workspace API key in OpenClaw auth profiles.
- Discover available execution models from `/v1/models`.
- Send an execution request with server-side automatic routing.
- Pin a request to a specific provider with `--provider`.
- Add simple routing hints with `--label key=value`.
- Inspect balance, explain `402` responses, and resume top-up flows.
- Inspect recent prepaid usage and caller ledger activity.

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
- When routing fails, explain the server-side reason in plain language.
- Treat structured `402 Payment Required` as a guided recovery state, not a
  generic transport failure.
- Keep 402 recovery inside OpenClaw until the required Stripe checkout step.
- Keep billing state honest: prefer server-provided authoritative balance
  reads, keep 402 snapshots and top-up session state as supporting context, and
  clearly label any local fallback as last-known or estimated.

## Trust And Secrets

- Treat `OPENMARLIN_SERVER_URL` as the only trusted API origin for OpenMarlin registration, key bootstrap, routing, balance, and top-up calls, and keep it as the bare origin without `/v1`.
- Treat browser handoff URLs as trusted only when they come directly from the server contract in `handoff.authorization_url`.
- Do not reconstruct, guess, or rewrite WorkOS or web handoff URLs from device codes, callback state, copied text, or unrelated user input.
- If the server does not return `handoff.authorization_url`, stop treating browser handoff as ready and explain that the deployment is missing the required server-side contract.
- Treat future browser or web glue surfaces as trusted only when they are explicitly referenced by the trusted server response or by documented deployment configuration owned by the same operator.
- Never ask the user to paste platform API keys into chat if the skill can store or load them through OpenClaw auth profiles.
- Store issued platform API keys only in OpenClaw auth-profile storage, not in ordinary skill config, free-form notes, or browser URL parameters.
- Treat `OPENMARLIN_PLATFORM_API_KEY` as a temporary operator override for local debugging, not the preferred long-term storage path.
- Do not send platform API keys to browser handoff URLs, Stripe checkout URLs, or any origin other than the configured OpenMarlin server.
- When reporting status back to the user, show where the key was stored or loaded from, but do not echo the raw secret unless the active command explicitly returns it.

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

For browser handoff, registration sessions may also expose:

- `handoff.authorization_url`
- `handoff.redirect_uri`

OpenClaw should use the server-provided `authorization_url` directly rather
than reconstructing WorkOS entry URLs locally.

When platform balance is insufficient, server-side request flows may return a
structured `402` payload:

- `error_code = insufficient_balance`
- `message`
- `workspace_id`
- `current_balance.amount / unit`
- `required_balance.amount / unit`

That 402 contract should drive recovery UX instead of generic error handling.

For native OpenClaw execution through OpenMarlin, the caller-facing contract is:

- `POST /v1/executions`

The execution request currently supports:

- `instruction`
- `kind = agent_run`
- `stream`
- `provider_id`
- `labels`
- `agent_id`
- `session_key`
- `timeout_ms`
- `provider`
- `model`
- `metadata`

Execution responses return either:

- terminal JSON with `request_id`, `output`, optional `metadata`, and optional `streamed_text`
- or SSE events:
  `execution.start`
  `execution.chunk`
  `execution.end`
  `execution.error`

For Stripe-backed top-up state, the public top-up contract is:

- `POST /v1/topup/sessions`
- `GET /v1/topup/sessions/:sessionId`

Top-up sessions expose:

- `topup_session_id`
- `workspace_id`
- `requested_amount.amount / unit`
- `status = pending_payment | credit_applied | payment_failed`
- `created_at`
- `completed_at`
- `stripe_reference`
- `checkout_url`
- `credited_ledger_entry_id`

For current balance reads, the public authenticated balance contract is:

- `GET /v1/balance`

For recent caller billing history, the public authenticated billing contracts are:

- `GET /v1/usage-events`
- `GET /v1/ledger`

Inside OpenClaw, balance management should therefore use:

- `GET /v1/balance` as the primary exact balance source
- the last server-provided structured `402` balance snapshot as supporting context
- tracked top-up session state for the current workspace
- `credited_ledger_entry_id` to show when a Stripe-backed credit has landed
- `GET /v1/usage-events` and `GET /v1/ledger` for recent caller billing activity

## Setup

Required:

```bash
export OPENMARLIN_SERVER_URL="http://127.0.0.1:3000"
```

OpenClaw-persisted skill config is also supported. These helpers resolve
required and default values from:

1. process env
2. `~/.openclaw/openclaw.json` under
   `skills.entries["openmarlin"].env`

That means the user does not need to hand-edit config files as long as
OpenClaw writes the skill config on their behalf.

Optional direct API key override:

```bash
export OPENMARLIN_PLATFORM_API_KEY="claw_wsk_..."
```

After bootstrap, this env var is no longer required if you store the key into
OpenClaw auth profiles.

Optional request-routing defaults:

```bash
export OPENMARLIN_DEFAULT_PROVIDER_ID="node-a"
export OPENMARLIN_DEFAULT_ROUTING_LABELS='{"region":"ap-sg"}'
```

If the server does not return `handoff.authorization_url`, keep the user in
OpenClaw, surface the device code or callback state, and explain that the
deployment is missing the required server-side WorkOS handoff URL contract.

## Playbooks

- For first-time setup, start with `registration_session.py create`, prefer the
  default `device` flow, then continue through `watch` and `bootstrap --store`
  instead of stopping at browser handoff.
- If the user already has a registration session ID, resume with `status` or
  `watch` rather than creating a fresh session. If it is `expired`, start over.
- For structured `402` recovery, treat the payload as workflow input: explain
  balance and shortfall, create or resume the top-up session, and keep the
  checkout URL plus `status` / `watch` command visible.
- After Stripe checkout, use top-up `status` or `watch` until the session is
  `credit_applied`, then refresh the authoritative balance and point the user
  back to the original request.

## Commands

Create a default device-style session:

```bash
python3 scripts/registration_session.py create
```

When the server returns `handoff.authorization_url`, this command should
attempt to open it in the system browser automatically, then print the session
ID, any device code, and the `watch` command to continue in OpenClaw.

Dry-run the registration setup without creating a session:

```bash
python3 scripts/registration_session.py --server-url https://your-server.example.com create --dry-run
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

Explain a structured 402 response and get the next recovery steps:

```bash
python3 scripts/billing.py explain-402 \
  --response-json '{"error_code":"insufficient_balance","message":"Workspace balance is insufficient for this request.","workspace_id":"ws_123","current_balance":{"amount":0,"unit":"credits"},"required_balance":{"amount":1,"unit":"credits"}}'
```

Dry-run 402 recovery setup without creating anything:

```bash
python3 scripts/billing.py explain-402 \
  --dry-run \
  --server-url https://your-server.example.com \
  --api-key claw_wsk_placeholder \
  --response-json '{"error_code":"insufficient_balance","message":"Workspace balance is insufficient for this request.","workspace_id":"ws_123","current_balance":{"amount":0,"unit":"credits"},"required_balance":{"amount":1,"unit":"credits"}}'
```

Explain a structured 402 response and immediately create the top-up session:

```bash
python3 scripts/billing.py explain-402 \
  --auto-recover \
  --response-json '{"error_code":"insufficient_balance","message":"Workspace balance is insufficient for this request.","workspace_id":"ws_123","current_balance":{"amount":0,"unit":"credits"},"required_balance":{"amount":1,"unit":"credits"}}'
```

Create a top-up session directly from the 402 shortfall:

```bash
python3 scripts/billing.py create-topup \
  --response-json '{"error_code":"insufficient_balance","message":"Workspace balance is insufficient for this request.","workspace_id":"ws_123","current_balance":{"amount":0,"unit":"credits"},"required_balance":{"amount":1,"unit":"credits"}}'
```

Check or wait on a top-up session:

```bash
python3 scripts/billing.py status --session-id <topup-session-id>
python3 scripts/billing.py watch --session-id <topup-session-id>
```

Show the current authoritative balance for the authenticated workspace:

```bash
python3 scripts/billing.py balance --workspace-id <workspace-id>
```

Refresh local 402 context first, then fetch and store the authoritative balance:

```bash
python3 scripts/billing.py balance \
  --response-json '{"error_code":"insufficient_balance","message":"Workspace balance is insufficient for this request.","workspace_id":"ws_123","current_balance":{"amount":0,"unit":"credits"},"required_balance":{"amount":1,"unit":"credits"}}'
```

Show tracked top-up history from local OpenClaw billing state:

```bash
python3 scripts/billing.py history --workspace-id <workspace-id>
```

Show recent caller billing activity from the server usage-event and ledger APIs:

```bash
python3 scripts/billing.py activity
```

List currently available execution models before choosing a model id:

```bash
python3 scripts/platform_request.py models
```

If you omit `model`, `/v1/executions` lets the server choose both model and
provider automatically. If you do pass `model`, use the exact full ref returned
by `python3 scripts/platform_request.py models`, for example
`openai-codex/gpt-5.4`, rather than a bare id like `gpt-5.4`.

If you pass both `--provider` and an exact `model`, first confirm that the same
`models` output shows that provider under that exact model ref.

Send an authenticated `/v1/executions` request and let the server choose model
and provider automatically:

```bash
python3 scripts/platform_request.py executions \
  --body-json '{"instruction":"say hello"}'
```

Send an authenticated `/v1/executions` request with an exact model but
automatic provider routing:

```bash
python3 scripts/platform_request.py executions \
  --body-json '{"instruction":"say hello","model":"openai-codex/gpt-5.4"}'
```

Dry-run a routed request without sending it:

```bash
python3 scripts/platform_request.py executions \
  --dry-run \
  --server-url https://your-server.example.com \
  --api-key claw_wsk_placeholder \
  --body-json '{"instruction":"say hello"}'
```

Send an authenticated `/v1/executions` request with an explicit provider
override:

```bash
python3 scripts/platform_request.py executions \
  --provider node-a \
  --body-json '{"instruction":"say hello"}'
```

Send an authenticated `/v1/executions` request with both an explicit provider
and an exact model:

First use `python3 scripts/platform_request.py models` and verify that
`node-a` appears under `openai-codex/gpt-5.4`, then send:

```bash
python3 scripts/platform_request.py executions \
  --provider node-a \
  --body-json '{"instruction":"say hello","model":"openai-codex/gpt-5.4"}'
```

Send a request with simple routing hints and let the server narrow the route:

```bash
python3 scripts/platform_request.py executions \
  --label region=ap-sg \
  --label tier=premium \
  --body-json '{"instruction":"summarize this"}'
```

Request streaming execution updates over SSE:

```bash
python3 scripts/platform_request.py executions \
  --body-json '{"instruction":"say hello","stream":true}'
```

Invoke a registered remote skill with automatic provider selection:

```bash
python3 scripts/platform_request.py invoke \
  --skill demo.echo \
  --input-json '{"text":"hello"}'
```

Invoke a registered remote skill with an explicit provider override:

```bash
python3 scripts/platform_request.py invoke \
  --skill demo.echo \
  --provider node-a \
  --input-json '{"text":"hello"}'
```

## Credential Handling

The returned `secret` is the steady-state platform credential for OpenClaw.

- prefer OpenClaw auth profiles over plain repo files or ordinary config
- store the key in `~/.openclaw/agents/<agentId>/agent/auth-profiles.json`
  using the default profile `openmarlin-platform:default`
- after storing with `--store`, later `platform_request.py` calls can reuse the
  key automatically without re-exporting it
- do not write the key into ordinary `openclaw.json` fields
- if you only need to hand it off manually, use process env or operator-managed
  secret storage rather than chat history when possible

## Routing Failure Guidance

Translate common server responses into plain language:

- `provider_unavailable`: the selected provider is not currently connected
- `provider_route_not_found`: the server could not find any eligible provider
  for the requested skill route
- `execution_provider_not_found`: the server could not find any eligible
  execution provider for the requested kind/model/labels/default route
- `execution_provider_ambiguous`: more than one execution provider matched and
  the server needs narrower labels or an explicit provider override
- `provider_label_mismatch`: the provider does not satisfy the requested routing
  hints
- `skill_not_available_on_provider`: that provider does not expose the requested
  skill
- `skill_not_available`: no connected provider currently exposes that skill
- `execution_kind_not_available`: the provider is connected but does not expose
  the requested execution kind
- `invalid_routing_labels`: the label hints were not valid JSON or `key=value`
  pairs

## 402 Recovery Guidance

When the server returns a structured `402 insufficient_balance` response:

- show the current balance, required balance, and shortfall explicitly
- tell the user this is a recoverable billing state, not a broken request
- prefer `explain-402 --auto-recover` when the user wants you to carry them directly into the next step
- offer the next two actions inside OpenClaw:
  `python3 scripts/billing.py create-topup ...`
  `python3 scripts/billing.py watch --session-id <topup-session-id>`
- persist the `current_balance` snapshot into OpenClaw billing state so later explanations have server-sourced context
- keep the browser handoff limited to the returned Stripe `checkout_url`

Do not flatten this into “request failed” or “transport error”.

## Top-up And Balance Guidance

When guiding a user through top-up or billing state:

- start from OpenClaw prompts or helper commands, not a website-first billing page
- create the top-up session inside OpenClaw
- show the distinction between:
  `pending_payment`
  `credit_applied`
  `payment_failed`
- when payment is still pending, tell the user the only external step is opening the Stripe `checkout_url`
- when payment completes and `credited_ledger_entry_id` appears, show that the Stripe funding has been turned into a platform ledger credit
- refresh the authoritative balance view with `GET /v1/balance` after completion
- keep local billing-state snapshots as fallback and historical context, not the primary balance answer

When these happen, keep the explanation concrete:

- restate the provider and labels you actually sent
- say whether the user should retry with a different provider, different labels,
  or no labels
