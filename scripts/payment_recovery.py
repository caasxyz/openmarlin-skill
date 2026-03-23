#!/usr/bin/env python3
"""Guided 402 recovery and top-up helpers for claw-federation."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from openclaw_skill_config import get_skill_env
from openclaw_billing_state import (
    get_last_balance_snapshot,
    list_topup_sessions,
    record_balance_snapshot,
    record_topup_session,
)
from openclaw_platform_auth import DEFAULT_AGENT_ID, DEFAULT_PROFILE_ID, resolve_platform_api_key


DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_POLL_INTERVAL_SECONDS = 2.0


def parse_args() -> argparse.Namespace:
    default_server_url, _server_url_source = get_skill_env("CLAW_FEDERATION_SERVER_URL")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--server-url",
        default=(default_server_url or "").strip(),
        help="Base URL for claw-federation-server. Defaults to CLAW_FEDERATION_SERVER_URL, then OpenClaw skill config.",
    )
    common.add_argument(
        "--api-key",
        default=os.environ.get("CLAW_FEDERATION_PLATFORM_API_KEY", "").strip(),
        help="Platform API key. Defaults to CLAW_FEDERATION_PLATFORM_API_KEY, then OpenClaw auth-profiles.json.",
    )
    common.add_argument(
        "--profile-id",
        default=DEFAULT_PROFILE_ID,
        help=f"OpenClaw auth profile ID used when resolving a stored platform key. Default: {DEFAULT_PROFILE_ID}.",
    )
    common.add_argument(
        "--agent-id",
        default=DEFAULT_AGENT_ID,
        help=f"OpenClaw agent ID used when resolving a stored platform key. Default: {DEFAULT_AGENT_ID}.",
    )
    common.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON output when possible.",
    )

    parser = argparse.ArgumentParser(
        description="Handle structured 402 recovery and top-up flows for claw-federation.",
        parents=[common],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    explain = subparsers.add_parser("explain-402", help="Explain a structured 402 response.", parents=[common])
    explain.add_argument("--response-json", help="Raw JSON object payload for the 402 response.")
    explain.add_argument("--response-file", help="Path to a JSON file containing the 402 response.")

    create = subparsers.add_parser("create-topup", help="Create a top-up session.", parents=[common])
    create.add_argument("--amount", type=float, help="Requested top-up amount in credits.")
    create.add_argument("--response-json", help="Optional 402 response JSON used to derive a suggested amount.")
    create.add_argument("--response-file", help="Optional 402 response JSON file used to derive a suggested amount.")

    balance = subparsers.add_parser("balance", help="Show the last known balance snapshot for a workspace.", parents=[common])
    balance.add_argument("--workspace-id", help="Workspace ID. Defaults to the workspace from a supplied 402 response.")
    balance.add_argument("--response-json", help="Optional structured 402 response JSON used to refresh the stored snapshot first.")
    balance.add_argument("--response-file", help="Optional structured 402 response JSON file used to refresh the stored snapshot first.")

    history = subparsers.add_parser("history", help="Show tracked top-up sessions for a workspace.", parents=[common])
    history.add_argument("--workspace-id", help="Optional workspace ID filter.")
    history.add_argument("--limit", type=int, default=10, help="Maximum sessions to show. Default: 10.")

    status = subparsers.add_parser("status", help="Fetch the current top-up session state.", parents=[common])
    status.add_argument("--session-id", required=True, help="Top-up session ID.")

    watch = subparsers.add_parser("watch", help="Wait for a top-up session to complete or fail.", parents=[common])
    watch.add_argument("--session-id", required=True, help="Top-up session ID.")
    watch.add_argument(
        "--interval-seconds",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help=f"Polling interval in seconds. Default: {DEFAULT_POLL_INTERVAL_SECONDS}.",
    )
    watch.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Maximum total wait time in seconds. Default: {DEFAULT_TIMEOUT_SECONDS}.",
    )

    return parser.parse_args()


def require_non_empty(value: str, message: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise SystemExit(message)
    return normalized


def resolve_api_key_or_exit(raw_api_key: str, profile_id: str, agent_id: str) -> tuple[str, str]:
    if raw_api_key.strip():
        return raw_api_key.strip(), "env-or-flag"

    key, _profile, auth_store_path = resolve_platform_api_key(profile_id=profile_id, agent_id=agent_id)
    if key:
        return key, f"auth-profiles:{auth_store_path}"

    raise SystemExit(
        "Missing platform API key. Set CLAW_FEDERATION_PLATFORM_API_KEY, pass --api-key, "
        "or bootstrap and store a key first."
    )


def load_json_object(raw: str, *, source: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SystemExit(f"Invalid JSON in {source}: {error}") from error
    if not isinstance(parsed, dict):
        raise SystemExit(f"{source} must decode to a JSON object.")
    return parsed


def load_json_object_from_option(raw: str | None, path: str | None, *, source_name: str) -> dict[str, Any]:
    if bool(raw) == bool(path):
        raise SystemExit(f"Provide exactly one of {source_name}-json or {source_name}-file.")
    if raw:
        return load_json_object(raw, source=f"--{source_name}-json")
    with open(path, "r", encoding="utf-8") as handle:
        return load_json_object(handle.read(), source=f"--{source_name}-file")


def request_json(url: str, method: str = "GET", headers: dict[str, str] | None = None, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any] | str]:
    body = None
    merged_headers = {"Accept": "application/json"}
    if headers:
        merged_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        merged_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, method=method, headers=merged_headers)
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        try:
            payload_obj = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload_obj = raw
        return error.code, payload_obj
    except urllib.error.URLError as error:
        raise SystemExit(f"Request failed for {method} {url}: {error.reason}") from error


def parse_insufficient_balance(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("error_code") != "insufficient_balance":
        return None

    current = payload.get("current_balance")
    required = payload.get("required_balance")
    if not isinstance(current, dict) or not isinstance(required, dict):
        return None

    current_amount = current.get("amount")
    required_amount = required.get("amount")
    unit = current.get("unit")
    if not isinstance(current_amount, (int, float)) or not isinstance(required_amount, (int, float)):
        return None
    if not isinstance(unit, str) or unit != required.get("unit"):
        return None

    shortfall = max(float(required_amount) - float(current_amount), 0.0)
    return {
        "workspace_id": payload.get("workspace_id"),
        "message": payload.get("message"),
        "current_balance": {"amount": float(current_amount), "unit": unit},
        "required_balance": {"amount": float(required_amount), "unit": unit},
        "shortfall": {"amount": shortfall, "unit": unit},
    }


def build_recovery_commands(summary: dict[str, Any]) -> list[str]:
    amount = summary["shortfall"]["amount"]
    rendered_amount = int(amount) if float(amount).is_integer() else amount
    return [
        f"python3 scripts/payment_recovery.py create-topup --amount {rendered_amount}",
        "python3 scripts/payment_recovery.py watch --session-id <topup-session-id>",
    ]


def derive_topup_amount(args: argparse.Namespace) -> float:
    if args.amount is not None:
        if args.amount <= 0:
            raise SystemExit("--amount must be greater than 0.")
        return args.amount

    payload = load_json_object_from_option(args.response_json, args.response_file, source_name="response")
    summary = parse_insufficient_balance(payload)
    if not summary:
        raise SystemExit("The provided response is not a structured insufficient_balance payload.")
    amount = summary["shortfall"]["amount"]
    return amount if amount > 0 else summary["required_balance"]["amount"]


def remember_402_summary(summary: dict[str, Any], *, agent_id: str) -> dict[str, Any]:
    workspace_id = summary.get("workspace_id")
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise SystemExit("Structured insufficient_balance payload is missing workspace_id.")
    return record_balance_snapshot(
        workspace_id=workspace_id,
        amount=summary["current_balance"]["amount"],
        unit=summary["current_balance"]["unit"],
        agent_id=agent_id,
        source="structured_402",
        estimated=False,
        message=summary.get("message"),
        required_amount=summary["required_balance"]["amount"],
        reference={"error_code": "insufficient_balance"},
    )


def update_balance_from_completed_topup(
    session: dict[str, Any],
    *,
    agent_id: str,
) -> dict[str, Any] | None:
    if session.get("status") != "credit_applied":
        return None

    workspace_id = session.get("workspace_id")
    requested_amount = session.get("requested_amount")
    if not isinstance(workspace_id, str) or not isinstance(requested_amount, dict):
        return None
    amount = requested_amount.get("amount")
    unit = requested_amount.get("unit")
    if not isinstance(amount, (int, float)) or not isinstance(unit, str):
        return None

    previous_snapshot, _state_path = get_last_balance_snapshot(workspace_id=workspace_id, agent_id=agent_id)
    if not previous_snapshot:
        return None
    previous_amount = previous_snapshot.get("amount")
    previous_unit = previous_snapshot.get("unit")
    if not isinstance(previous_amount, (int, float)) or previous_unit != unit:
        return None

    return record_balance_snapshot(
        workspace_id=workspace_id,
        amount=float(previous_amount) + float(amount),
        unit=unit,
        agent_id=agent_id,
        source="topup_session_credit_applied",
        estimated=bool(previous_snapshot.get("estimated")),
        message="Updated from a completed Stripe top-up session.",
        reference={
            "topup_session_id": session.get("topup_session_id"),
            "credited_ledger_entry_id": session.get("credited_ledger_entry_id"),
            "base_observed_at": previous_snapshot.get("observed_at"),
        },
    )


def print_402_summary(summary: dict[str, Any]) -> None:
    print(summary.get("message") or "Workspace balance is insufficient for this request.")
    print(f"Workspace ID: {summary.get('workspace_id', '<unknown>')}")
    print(
        f"Current balance: {summary['current_balance']['amount']} {summary['current_balance']['unit']}"
    )
    print(
        f"Required balance: {summary['required_balance']['amount']} {summary['required_balance']['unit']}"
    )
    print(f"Shortfall: {summary['shortfall']['amount']} {summary['shortfall']['unit']}")
    print("Recovery:")
    for command in build_recovery_commands(summary):
        print(f"  {command}")


def print_topup_session(payload: dict[str, Any]) -> None:
    print(f"Top-up session ID: {payload.get('topup_session_id', '<unknown>')}")
    print(f"Workspace ID: {payload.get('workspace_id', '<unknown>')}")
    requested_amount = payload.get("requested_amount")
    if isinstance(requested_amount, dict):
        print(
            f"Requested amount: {requested_amount.get('amount', '<unknown>')} {requested_amount.get('unit', '<unknown>')}"
        )
    print(f"Status: {payload.get('status', '<unknown>')}")
    print(f"Created at: {payload.get('created_at', '<unknown>')}")
    print(f"Completed at: {payload.get('completed_at', '<unknown>')}")
    print(f"Stripe reference: {payload.get('stripe_reference', '<unknown>')}")
    print(f"Checkout URL: {payload.get('checkout_url', '<unknown>')}")
    print(f"Credited ledger entry ID: {payload.get('credited_ledger_entry_id', '<unknown>')}")
    print("Next step: open the checkout URL only for the Stripe payment step, then return to OpenClaw and watch the session.")


def print_balance_snapshot(snapshot: dict[str, Any], state_path: str) -> None:
    print(f"Workspace ID: {snapshot.get('workspace_id', '<unknown>')}")
    print(f"Last known balance: {snapshot.get('amount', '<unknown>')} {snapshot.get('unit', '<unknown>')}")
    print(f"Observed at: {snapshot.get('observed_at', '<unknown>')}")
    print(f"Source: {snapshot.get('source', '<unknown>')}")
    print(f"Estimated: {'yes' if snapshot.get('estimated') else 'no'}")
    required_amount = snapshot.get("required_amount")
    if required_amount is not None:
        print(f"Required balance from last 402: {required_amount} {snapshot.get('unit', '<unknown>')}")
    message = snapshot.get("message")
    if message:
        print(f"Message: {message}")
    print(f"Billing state path: {state_path}")


def print_history(sessions: list[dict[str, Any]], state_path: str) -> None:
    print(f"Billing state path: {state_path}")
    if not sessions:
        print("Tracked top-up sessions: none")
        return
    print("Tracked top-up sessions:")
    for session in sessions:
        amount = session.get("requested_amount")
        rendered_amount = "<unknown>"
        if isinstance(amount, dict):
            rendered_amount = f"{amount.get('amount', '<unknown>')} {amount.get('unit', '<unknown>')}"
        print(
            f"- {session.get('topup_session_id', '<unknown>')} "
            f"workspace={session.get('workspace_id', '<unknown>')} "
            f"status={session.get('status', '<unknown>')} "
            f"amount={rendered_amount} "
            f"credited_ledger_entry_id={session.get('credited_ledger_entry_id', '<unknown>')}"
        )


def main() -> int:
    args = parse_args()

    if args.command == "explain-402":
        payload = load_json_object_from_option(args.response_json, args.response_file, source_name="response")
        summary = parse_insufficient_balance(payload)
        if not summary:
            raise SystemExit("The provided response is not a structured insufficient_balance payload.")
        stored = remember_402_summary(summary, agent_id=args.agent_id)
        if args.json:
            print(
                json.dumps(
                    {
                        "recovery": summary,
                        "commands": build_recovery_commands(summary),
                        "stored": stored,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print_402_summary(summary)
            print(f"Saved billing snapshot to: {stored['billing_state_path']}")
        return 0

    if args.command == "balance":
        summary = None
        if args.response_json or args.response_file:
            payload = load_json_object_from_option(args.response_json, args.response_file, source_name="response")
            summary = parse_insufficient_balance(payload)
            if not summary:
                raise SystemExit("The provided response is not a structured insufficient_balance payload.")
            remember_402_summary(summary, agent_id=args.agent_id)

        workspace_id = args.workspace_id or (summary.get("workspace_id") if summary else None)
        if not workspace_id:
            raise SystemExit("Missing workspace ID. Pass --workspace-id or provide a structured 402 response.")
        snapshot, state_path = get_last_balance_snapshot(workspace_id=workspace_id, agent_id=args.agent_id)
        if not snapshot:
            raise SystemExit(f"No stored balance snapshot for workspace {workspace_id}.")
        if args.json:
            print(json.dumps({"ok": True, "billing_state_path": state_path, "balance": snapshot}, indent=2, sort_keys=True))
        else:
            print_balance_snapshot(snapshot, state_path)
        return 0

    if args.command == "history":
        sessions, state_path = list_topup_sessions(workspace_id=args.workspace_id, agent_id=args.agent_id)
        sessions = sessions[: max(args.limit, 0)]
        if args.json:
            print(json.dumps({"ok": True, "billing_state_path": state_path, "sessions": sessions}, indent=2, sort_keys=True))
        else:
            print_history(sessions, state_path)
        return 0

    server_url = require_non_empty(
        args.server_url,
        "Missing server URL. Set CLAW_FEDERATION_SERVER_URL or pass --server-url.",
    ).rstrip("/")

    api_key, api_key_source = resolve_api_key_or_exit(args.api_key, args.profile_id, args.agent_id)
    auth_headers = {"Authorization": f"Bearer {api_key}"}

    if args.command == "create-topup":
        amount = derive_topup_amount(args)
        status, payload = request_json(
            f"{server_url}/v1/topup/sessions",
            method="POST",
            headers=auth_headers,
            payload={"amount": amount},
        )
    elif args.command == "status":
        status, payload = request_json(
            f"{server_url}/v1/topup/sessions/{urllib.parse.quote(args.session_id)}",
            headers=auth_headers,
        )
    elif args.command == "watch":
        deadline = time.monotonic() + args.timeout_seconds
        payload = {}
        status = 0
        while True:
            status, payload = request_json(
                f"{server_url}/v1/topup/sessions/{urllib.parse.quote(args.session_id)}",
                headers=auth_headers,
            )
            if status >= 400:
                break
            if isinstance(payload, dict) and payload.get("status") in {"credit_applied", "payment_failed"}:
                break
            if time.monotonic() >= deadline:
                raise SystemExit(
                    f"Timed out after {args.timeout_seconds:.1f}s waiting for top-up session {args.session_id}."
                )
            time.sleep(args.interval_seconds)
    else:
        raise SystemExit(f"Unsupported command: {args.command}")

    if status >= 400:
        if args.json:
            print(json.dumps({"ok": False, "status": status, "api_key_source": api_key_source, "response": payload}, indent=2, sort_keys=True))
        else:
            print(f"HTTP {status}: {payload}", file=sys.stderr)
        return 1

    if args.json:
        structured: dict[str, Any] = {"ok": True, "status": status, "api_key_source": api_key_source, "response": payload}
        if isinstance(payload, dict):
            stored_session = record_topup_session(session=payload, agent_id=args.agent_id)
            structured["stored_session"] = stored_session
            refreshed_balance = update_balance_from_completed_topup(payload, agent_id=args.agent_id)
            if refreshed_balance:
                structured["refreshed_balance"] = refreshed_balance
        print(json.dumps(structured, indent=2, sort_keys=True))
    else:
        if isinstance(payload, dict):
            record_topup_session(session=payload, agent_id=args.agent_id)
            refreshed_balance = update_balance_from_completed_topup(payload, agent_id=args.agent_id)
            print_topup_session(payload)
            if refreshed_balance:
                snapshot = refreshed_balance["snapshot"]
                print(
                    "Refreshed last known balance: "
                    f"{snapshot['amount']} {snapshot['unit']} "
                    f"(estimated={'yes' if snapshot['estimated'] else 'no'})"
                )
        else:
            print(payload)

    return 0


if __name__ == "__main__":
    sys.exit(main())
