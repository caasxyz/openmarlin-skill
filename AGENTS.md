# AGENTS.md — claw-federation-skill

## Project Goal
Implement the OpenClaw skill-side UX for the claw federation platform.

This repository owns the guided user flows that sit on top of
`claw-federation-server`, including:

- registration and account linking
- platform API key bootstrap
- provider selection and routing hints
- structured `402 Payment Required` recovery
- guided top-up and balance management

## Tech Stack
- Python
- OpenClaw skills
- GitHub issues for task tracking

## Workflow Rules

- Every commit should be associated with the relevant GitHub issue when one exists.
- After landing meaningful progress, update the linked issue with implementation status and verification notes.
- When a scoped issue is fully implemented, close that issue instead of leaving it open as stale follow-up.
- For larger changes, prefer creating a dedicated branch with the `codex/` prefix and land the work through a pull request instead of pushing directly to `main`.
- For smaller changes that still land directly, keep commits scoped and issue-linked.
- When using `gh` commands with long or Markdown-heavy bodies, prefer `--body-file` with a temporary file over inline `--body`.
- Do not embed Markdown containing backticks, `$()`, or complex quoting directly inside `zsh -lc` command strings unless there is a strong reason.
- For generated pull request bodies or issue comments, default to writing Markdown to `/tmp/*.md` and passing it via `--body-file`.

## Skill-side Constraints

- Keep the UX OpenClaw-first by default.
- Use browser handoff only for irreducible external steps such as WorkOS auth or Stripe checkout.
- Do not invent server contracts that do not exist.
- When balance or ledger state is only partially observable from public APIs, label the OpenClaw view as last-known or estimated instead of pretending it is authoritative.
- Do not store platform API keys in ordinary plain config when auth-profile storage is available.

## Common Safe Command Prefixes

These are the command families most commonly needed in this repository and are
usually safe candidates for persistent approval when the user wants to reduce
repeat prompts:

- `git add`
- `git commit -m`
- `git push origin`
- `git switch`
- `gh issue list`
- `gh issue view`
- `gh issue comment`
- `gh issue close`
- `gh pr list`
- `gh pr view`
- `gh pr checks`
- `pnpm test`
- `pnpm build`
- `pnpm lint`
- `curl -s http://127.0.0.1:...`
- `curl -s -X POST http://127.0.0.1:...`

For local validation, these localhost-oriented commands are also common:

- `python3 scripts/registration_session.py ...`
- `python3 scripts/platform_request.py ...`
- `python3 scripts/payment_recovery.py ...`
- `PORT=312x node --import tsx src/index.ts` in the server repo

Do not request broad approvals when a narrower prefix will do. Prefer the
smallest stable prefix that covers the repeated workflow.
