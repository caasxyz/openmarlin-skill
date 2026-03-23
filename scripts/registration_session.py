#!/usr/bin/env python3
"""Helpers for claw-federation registration sessions."""

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


DEFAULT_POLL_INTERVAL_SECONDS = 2.0
DEFAULT_TIMEOUT_SECONDS = 300.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create, inspect, and poll claw-federation registration sessions."
    )
    parser.add_argument(
        "--server-url",
        default=os.environ.get("CLAW_FEDERATION_SERVER_URL", "").strip(),
        help="Base URL for claw-federation-server. Defaults to CLAW_FEDERATION_SERVER_URL.",
    )
    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON only.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser(
        "create",
        help="Create a registration session.",
        parents=[json_parent],
    )
    create_parser.add_argument(
        "--auth-flow",
        choices=("device", "workos_callback"),
        default="device",
        help="Registration auth flow. Default: device.",
    )

    status_parser = subparsers.add_parser(
        "status",
        help="Fetch the current session state.",
        parents=[json_parent],
    )
    status_parser.add_argument("--session-id", required=True, help="Registration session ID.")

    watch_parser = subparsers.add_parser(
        "watch",
        help="Poll until completion or expiration.",
        parents=[json_parent],
    )
    watch_parser.add_argument("--session-id", required=True, help="Registration session ID.")
    watch_parser.add_argument(
        "--interval-seconds",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help=f"Polling interval in seconds. Default: {DEFAULT_POLL_INTERVAL_SECONDS}.",
    )
    watch_parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Maximum total wait time in seconds. Default: {DEFAULT_TIMEOUT_SECONDS}.",
    )

    return parser.parse_args()


def require_server_url(raw: str) -> str:
    server_url = raw.strip().rstrip("/")
    if not server_url:
        raise SystemExit(
            "Missing server URL. Set CLAW_FEDERATION_SERVER_URL or pass --server-url."
        )
    return server_url


def request_json(url: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        message = raw or error.reason
        try:
            payload_obj = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload_obj = {"error": message}
        raise SystemExit(
            f"HTTP {error.code} for {method} {url}: {json.dumps(payload_obj, sort_keys=True)}"
        ) from error
    except urllib.error.URLError as error:
        raise SystemExit(f"Request failed for {method} {url}: {error.reason}") from error


def build_browser_url(session: dict[str, Any]) -> str | None:
    handoff = session.get("handoff")
    if not isinstance(handoff, dict):
        return None

    template: str | None
    if handoff.get("type") == "device":
        template = os.environ.get("CLAW_FEDERATION_WORKOS_DEVICE_URL_TEMPLATE")
    elif handoff.get("type") == "browser":
        template = os.environ.get("CLAW_FEDERATION_WORKOS_CALLBACK_URL_TEMPLATE")
    else:
        template = None

    if not template:
        return None

    replacements = {
        "callback_state": str(handoff.get("callback_state", "")),
        "device_code": str(handoff.get("device_code", "")),
        "registration_session_id": str(session.get("registration_session_id", "")),
    }
    for key, value in replacements.items():
        template = template.replace(f"{{{key}}}", urllib.parse.quote(value, safe=""))
    return template


def completion_summary(session: dict[str, Any]) -> list[str]:
    completion = session.get("completion")
    if not isinstance(completion, dict):
        return []

    workspace = completion.get("workspace")
    provider_identity = completion.get("provider_identity")
    credential_bootstrap = completion.get("credential_bootstrap")

    lines = [
        f"Account ID: {completion.get('account_id', '<unknown>')}",
        f"New account: {completion.get('is_new_account', '<unknown>')}",
    ]

    if isinstance(workspace, dict):
        lines.extend(
            [
                f"Workspace ID: {workspace.get('workspace_id', '<unknown>')}",
                f"Workspace: {workspace.get('display_name', '<unknown>')} ({workspace.get('slug', '<unknown>')})",
            ]
        )

    if isinstance(provider_identity, dict):
        lines.extend(
            [
                f"Provider: {provider_identity.get('provider', '<unknown>')}",
                f"Provider subject: {provider_identity.get('provider_subject', '<unknown>')}",
            ]
        )
        primary_email = provider_identity.get("primary_email")
        if primary_email:
            lines.append(f"Primary email: {primary_email}")

    if isinstance(credential_bootstrap, dict):
        lines.append(
            f"Credential bootstrap: {credential_bootstrap.get('status', '<unknown>')}"
        )

    return lines


def print_session(session: dict[str, Any]) -> None:
    handoff = session.get("handoff")
    browser_url = build_browser_url(session)

    print(f"Session ID: {session.get('registration_session_id', '<unknown>')}")
    print(f"State: {session.get('state', '<unknown>')}")
    print(f"Auth flow: {session.get('auth_flow', '<unknown>')}")
    print(f"Provider: {session.get('provider', '<unknown>')}")
    print(f"Created at: {session.get('created_at', '<unknown>')}")
    print(f"Expires at: {session.get('expires_at', '<unknown>')}")

    if isinstance(handoff, dict):
        print(f"Handoff type: {handoff.get('type', '<unknown>')}")
        if handoff.get("device_code"):
            print(f"Device code: {handoff.get('device_code')}")
        if handoff.get("callback_state"):
            print(f"Callback state: {handoff.get('callback_state')}")

    if browser_url:
        print(f"Browser URL: {browser_url}")
    elif session.get("state") == "pending_external_auth":
        print("Browser URL: <not configured>")

    completion_lines = completion_summary(session)
    if completion_lines:
        print("Completion:")
        for line in completion_lines:
            print(f"  {line}")
    elif session.get("state") == "pending_external_auth":
        print("Completion: waiting for external auth")


def create_session(server_url: str) -> dict[str, Any]:
    command = args.command
    assert command == "create"
    return request_json(
        f"{server_url}/v1/registration/sessions",
        method="POST",
        payload={"provider": "workos", "auth_flow": args.auth_flow},
    )


def fetch_session(server_url: str, session_id: str) -> dict[str, Any]:
    return request_json(f"{server_url}/v1/registration/sessions/{urllib.parse.quote(session_id)}")


def watch_session(server_url: str, session_id: str, interval_seconds: float, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        session = fetch_session(server_url, session_id)
        state = session.get("state")
        if state in {"completed", "expired"}:
            return session
        if time.monotonic() >= deadline:
            raise SystemExit(
                f"Timed out after {timeout_seconds:.1f}s waiting for session {session_id}."
            )
        time.sleep(interval_seconds)


args = parse_args()


def main() -> int:
    server_url = require_server_url(args.server_url)

    if args.command == "create":
        session = create_session(server_url)
    elif args.command == "status":
        session = fetch_session(server_url, args.session_id)
    elif args.command == "watch":
        session = watch_session(
            server_url,
            args.session_id,
            args.interval_seconds,
            args.timeout_seconds,
        )
    else:
        raise SystemExit(f"Unsupported command: {args.command}")

    if args.json:
        print(json.dumps(session, indent=2, sort_keys=True))
    else:
        print_session(session)

    return 3 if session.get("state") == "expired" else 0


if __name__ == "__main__":
    sys.exit(main())
