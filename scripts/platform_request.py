#!/usr/bin/env python3
"""Authenticated OpenMarlin platform requests with routing hints."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from openclaw_skill_config import (
    build_server_connection_error,
    get_skill_env,
    probe_server_openapi,
    require_server_url,
)
from openclaw_billing_state import record_balance_snapshot
from openclaw_platform_auth import DEFAULT_AGENT_ID, DEFAULT_PROFILE_ID, resolve_platform_api_key
from payment_recovery import build_recovery_commands, parse_insufficient_balance


JsonValue = Any


ERROR_HELP = {
    "missing_api_key": "Missing platform API key. Export OPENMARLIN_PLATFORM_API_KEY first.",
    "invalid_api_key": "The platform API key was rejected. Re-bootstrap a fresh key and retry.",
    "api_key_inactive": "The platform API key is no longer active. Bootstrap a replacement key.",
    "workspace_missing": "The API key resolved, but its workspace no longer exists on the server.",
    "account_missing": "The API key resolved, but its owning account no longer exists on the server.",
    "invalid_routing_labels": "Routing labels were invalid. Use repeated --label key=value flags or valid JSON in OPENMARLIN_DEFAULT_ROUTING_LABELS.",
    "provider_unavailable": "The selected provider is not currently connected.",
    "provider_label_mismatch": "The selected provider does not satisfy the requested routing hints.",
    "execution_provider_not_found": "The server could not find any eligible execution provider for this request. Retry with different labels, a different model, or an explicit --provider override.",
    "execution_provider_ambiguous": "More than one eligible execution provider matched and the server could not choose automatically. Retry with narrower labels or an explicit --provider override.",
    "execution_kind_not_available": "The selected provider does not support the requested execution kind.",
    "skill_not_available": "No connected provider currently exposes that skill.",
    "skill_not_available_on_provider": "That provider does not expose the requested skill.",
    "invalid_request": "The request payload did not match the server contract.",
}


def parse_args() -> argparse.Namespace:
    default_server_url, server_url_source = get_skill_env("OPENMARLIN_SERVER_URL")
    default_api_key, _api_key_source = get_skill_env("OPENMARLIN_PLATFORM_API_KEY")
    default_provider, provider_source = get_skill_env("OPENMARLIN_DEFAULT_PROVIDER_ID")
    common = argparse.ArgumentParser(add_help=False)
    common.set_defaults(_server_url_source=server_url_source, _provider_source=provider_source)
    common.add_argument(
        "--server-url",
        default=(default_server_url or "").strip(),
        help="Base URL for the OpenMarlin server. Defaults to OPENMARLIN_SERVER_URL, then OpenClaw skill config.",
    )
    common.add_argument(
        "--api-key",
        default=(default_api_key or "").strip(),
        help="Platform API key. Defaults to OPENMARLIN_PLATFORM_API_KEY, then OpenClaw auth-profiles.json.",
    )
    common.add_argument(
        "--provider",
        default=(default_provider or "").strip(),
        help="Optional explicit provider override. Defaults to OPENMARLIN_DEFAULT_PROVIDER_ID, then OpenClaw skill config.",
    )
    common.add_argument(
        "--label",
        action="append",
        default=[],
        help="Routing hint in key=value form. May be repeated.",
    )
    common.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON output when possible.",
    )
    common.add_argument(
        "--dry-run",
        action="store_true",
        help="Show resolved configuration and a lightweight connectivity check without executing the request.",
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

    parser = argparse.ArgumentParser(
        description="Send authenticated OpenMarlin platform requests with optional provider overrides and routing hints.",
        parents=[common],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    executions = subparsers.add_parser(
        "executions",
        help="Send a /v1/executions request.",
        parents=[common],
    )
    executions.add_argument(
        "--body-json",
        help="Raw JSON object payload for /v1/executions.",
    )
    executions.add_argument(
        "--body-file",
        help="Path to a JSON file containing the /v1/executions payload.",
    )

    invoke = subparsers.add_parser(
        "invoke",
        help="Send an authenticated /invoke request.",
        parents=[common],
    )
    invoke.add_argument("--skill", required=True, help="Remote skill name.")
    invoke.add_argument(
        "--input-json",
        help="JSON object payload for the skill input.",
    )
    invoke.add_argument(
        "--input-file",
        help="Path to a JSON file containing the skill input object.",
    )

    subparsers.add_parser(
        "models",
        help="List currently available execution models from /v1/models.",
        parents=[common],
    )

    return parser.parse_args()


def require_non_empty(value: str, message: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise SystemExit(message)
    return normalized


def resolve_api_key(raw_api_key: str, profile_id: str, agent_id: str) -> tuple[str | None, str | None, str | None]:
    if raw_api_key.strip():
        return raw_api_key.strip(), "env-or-flag", None

    key, _profile, auth_store_path = resolve_platform_api_key(profile_id=profile_id, agent_id=agent_id)
    if key:
        return key, f"auth-profiles:{auth_store_path}", None

    return None, None, (
        "Missing platform API key. Set OPENMARLIN_PLATFORM_API_KEY, pass --api-key, "
        "or bootstrap with --store so the key is saved into OpenClaw auth-profiles.json."
    )


def resolve_api_key_or_exit(raw_api_key: str, profile_id: str, agent_id: str) -> tuple[str, str]:
    key, source, error = resolve_api_key(raw_api_key, profile_id, agent_id)
    if error:
        raise SystemExit(error)
    assert key is not None and source is not None
    return key, source


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


def parse_label_pairs(values: list[str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for raw in values:
        key, separator, value = raw.partition("=")
        key = key.strip()
        value = value.strip()
        if separator != "=" or not key or not value:
            raise SystemExit(f"Invalid --label value: {raw!r}. Expected key=value.")
        labels[key] = value
    return labels


def resolve_labels(cli_labels: list[str]) -> dict[str, str] | None:
    merged: dict[str, str] = {}
    env_raw, _source = get_skill_env("OPENMARLIN_DEFAULT_ROUTING_LABELS")
    env_raw = (env_raw or "").strip()
    if env_raw:
        env_labels = load_json_object(env_raw, source="OPENMARLIN_DEFAULT_ROUTING_LABELS")
        for key, value in env_labels.items():
            if not isinstance(key, str) or not isinstance(value, str) or not key or not value.strip():
                raise SystemExit(
                    "OPENMARLIN_DEFAULT_ROUTING_LABELS must be a JSON object of non-empty string values."
                )
            merged[key] = value.strip()

    merged.update(parse_label_pairs(cli_labels))
    return merged or None


def request(
    *,
    url: str,
    method: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> tuple[int, JsonValue, dict[str, str]]:
    body = json.dumps(payload).encode("utf-8")
    request_obj = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            **headers,
        },
    )
    try:
        with urllib.request.urlopen(request_obj) as response:
            content_type = response.headers.get("content-type", "")
            raw = response.read().decode("utf-8")
            payload_out: JsonValue
            if "application/json" in content_type and raw:
                payload_out = json.loads(raw)
            else:
                payload_out = raw
            return response.status, payload_out, dict(response.headers.items())
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        try:
            payload_out = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload_out = raw
        return error.code, payload_out, dict(error.headers.items())
    except urllib.error.URLError as error:
        parsed = urllib.parse.urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else url
        raise SystemExit(build_server_connection_error(base_url, str(error.reason))) from error


def request_without_body(
    *,
    url: str,
    method: str,
    headers: dict[str, str],
) -> tuple[int, JsonValue, dict[str, str]]:
    request_obj = urllib.request.Request(
        url,
        method=method,
        headers={
            "Accept": "application/json",
            **headers,
        },
    )
    try:
        with urllib.request.urlopen(request_obj) as response:
            content_type = response.headers.get("content-type", "")
            raw = response.read().decode("utf-8")
            payload_out: JsonValue
            if "application/json" in content_type and raw:
                payload_out = json.loads(raw)
            else:
                payload_out = raw
            return response.status, payload_out, dict(response.headers.items())
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8")
        try:
            payload_out = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload_out = raw
        return error.code, payload_out, dict(error.headers.items())
    except urllib.error.URLError as error:
        parsed = urllib.parse.urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else url
        raise SystemExit(build_server_connection_error(base_url, str(error.reason))) from error


def parse_sse_events(raw: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    event_type: str | None = None
    data_lines: list[str] = []

    def flush_event() -> None:
        nonlocal event_type, data_lines
        if event_type is None and not data_lines:
            return
        data_raw = "\n".join(data_lines)
        data_payload: Any = data_raw
        if data_raw:
            try:
                data_payload = json.loads(data_raw)
            except json.JSONDecodeError:
                data_payload = data_raw
        event: dict[str, Any] = {"event": event_type or "message", "data": data_payload}
        events.append(event)
        event_type = None
        data_lines = []

    for line in raw.splitlines():
        if not line.strip():
            flush_event()
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        value = value[1:] if separator and value.startswith(" ") else value
        if field == "event":
            event_type = value
        elif field == "data":
            data_lines.append(value)

    flush_event()
    return events


def explain_error(code: int, payload: JsonValue, provider: str | None, labels: dict[str, str] | None) -> str:
    if isinstance(payload, dict):
        recovery = parse_insufficient_balance(payload)
        if code == 402 and recovery:
            commands = build_recovery_commands(recovery)
            context_parts = []
            if provider:
                context_parts.append(f"provider={provider}")
            if labels:
                context_parts.append(f"labels={json.dumps(labels, sort_keys=True)}")
            context = f" Sent {', '.join(context_parts)}." if context_parts else ""
            return (
                f"HTTP 402 insufficient_balance: {recovery['message']} "
                f"Current={recovery['current_balance']['amount']} {recovery['current_balance']['unit']}, "
                f"required={recovery['required_balance']['amount']} {recovery['required_balance']['unit']}, "
                f"shortfall={recovery['shortfall']['amount']} {recovery['shortfall']['unit']}.{context} "
                f"Recovery: {commands[0]} then {commands[1]}"
            )
        error_code = payload.get("error")
        if isinstance(error_code, str):
            explanation = ERROR_HELP.get(error_code, "The server rejected the request.")
            context_parts = []
            if provider:
                context_parts.append(f"provider={provider}")
            if labels:
                context_parts.append(f"labels={json.dumps(labels, sort_keys=True)}")
            context = f" Sent {', '.join(context_parts)}." if context_parts else ""
            return f"HTTP {code} {error_code}: {explanation}{context}"
    return f"HTTP {code}: {payload}"


def iter_discovered_models(payload: JsonValue) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        models = payload.get("models")
        if isinstance(models, list):
            return [item for item in models if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def print_models_success(payload: JsonValue) -> None:
    models = iter_discovered_models(payload)
    if not models:
        print("Command: models")
        print("Response:")
        if isinstance(payload, str):
            print(payload)
        else:
            print(json.dumps(payload, indent=2, sort_keys=True))
        return

    print("Command: models")
    print(f"Available models: {len(models)}")
    for entry in models:
        model_id = entry.get("model") or entry.get("id") or entry.get("model_id") or "<unknown>"
        provider_id = entry.get("provider_id") or entry.get("provider") or "<unknown>"
        labels = entry.get("labels")
        if isinstance(labels, dict) and labels:
            print(f"- {model_id} via {provider_id} labels={json.dumps(labels, sort_keys=True)}")
        else:
            print(f"- {model_id} via {provider_id}")


def print_success(command: str, provider: str | None, labels: dict[str, str] | None, payload: JsonValue) -> None:
    if command == "models":
        print_models_success(payload)
        return

    print(f"Command: {command}")
    if provider:
        print(f"Provider override: {provider}")
    else:
        print("Provider override: <none; server-side automatic routing>")
    if labels:
        print(f"Routing labels: {json.dumps(labels, sort_keys=True)}")
    else:
        print("Routing labels: <none>")
    print("Response:")
    if isinstance(payload, str):
        print(payload)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))


def print_dry_run(args: argparse.Namespace, server_url: str, provider: str | None, labels: dict[str, str] | None) -> int:
    api_key, api_key_source, api_key_error = resolve_api_key(args.api_key, args.profile_id, args.agent_id)
    reachable, detail = probe_server_openapi(server_url)
    payload: dict[str, Any] = {
        "ok": reachable and api_key_error is None,
        "dry_run": True,
        "command": args.command,
        "server_url": server_url,
        "server_url_source": args._server_url_source or "flag-or-arg",
        "api_key_source": api_key_source,
        "api_key_error": api_key_error,
        "provider_override": provider,
        "provider_source": args._provider_source or ("flag-or-arg" if provider else None),
        "labels": labels or {},
        "connectivity": detail,
    }
    if args.command == "executions":
        body = load_json_object_from_option(args.body_json, args.body_file, source_name="body")
        payload["request_preview"] = {
            "kind": body.get("kind", "agent_run"),
            "model": body.get("model"),
            "stream": body.get("stream") is True,
            "has_instruction": isinstance(body.get("instruction"), str) and bool(body.get("instruction").strip()),
        }
    elif args.command == "invoke":
        input_payload = load_json_object_from_option(args.input_json, args.input_file, source_name="input")
        payload["skill"] = args.skill
        payload["input_keys"] = sorted(input_payload.keys())
    elif args.command == "models":
        payload["operation"] = "GET /v1/models"

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("Dry run only. No platform request was executed.")
        print(f"Command: {args.command}")
        print(f"Resolved server URL: {server_url}")
        print(f"Server URL source: {payload['server_url_source']}")
        print(f"Connectivity check: {detail}")
        if api_key_error:
            print(f"API key: missing ({api_key_error})")
        else:
            print(f"API key source: {api_key_source}")
        if args.command != "models":
            print(f"Provider override: {provider or '<none; server-side automatic routing>'}")
            print(f"Routing labels: {json.dumps(labels or {}, sort_keys=True)}")
        if args.command == "executions":
            preview = payload["request_preview"]
            print(f"Execution kind: {preview.get('kind', 'agent_run')}")
            print(f"Model: {preview.get('model', '<unknown>')}")
            print(f"Instruction present: {'yes' if preview.get('has_instruction') else 'no'}")
            print(f"Stream: {'yes' if preview.get('stream') else 'no'}")
        elif args.command == "models":
            print("Operation: GET /v1/models")
        else:
            print(f"Skill: {args.skill}")
            print(f"Input keys: {', '.join(payload['input_keys']) if payload['input_keys'] else '<none>'}")
    return 0 if payload["ok"] else 1


def main() -> int:
    args = parse_args()
    server_url = require_server_url(args.server_url)
    provider = args.provider.strip() or None
    labels = resolve_labels(args.label)
    if args.dry_run:
        return print_dry_run(args, server_url, provider, labels)
    api_key, api_key_source = resolve_api_key_or_exit(args.api_key, args.profile_id, args.agent_id)

    if args.command == "executions":
        body = load_json_object_from_option(args.body_json, args.body_file, source_name="body")
        if provider:
            body["provider_id"] = provider
        if labels:
            body["labels"] = labels
        status, payload, response_headers = request(
            url=f"{server_url}/v1/executions",
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            payload=body,
        )
    elif args.command == "invoke":
        input_payload = load_json_object_from_option(
            args.input_json,
            args.input_file,
            source_name="input",
        )
        body = {
            "skill": args.skill,
            "input": input_payload,
        }
        if provider:
            body["provider_id"] = provider
        if labels:
            body["labels"] = labels
        status, payload, response_headers = request(
            url=f"{server_url}/invoke",
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            payload=body,
        )
    elif args.command == "models":
        status, payload, response_headers = request_without_body(
            url=f"{server_url}/v1/models",
            method="GET",
            headers={
                "Authorization": f"Bearer {api_key}",
            },
        )
    else:
        raise SystemExit(f"Unsupported command: {args.command}")

    stream_events = None
    if (
        args.command == "executions"
        and isinstance(payload, str)
        and "text/event-stream" in response_headers.get("content-type", "")
    ):
        stream_events = parse_sse_events(payload)

    if status >= 400:
        message = explain_error(status, payload, provider, labels)
        recovery = parse_insufficient_balance(payload) if isinstance(payload, dict) else None
        stored_balance = None
        if recovery and isinstance(recovery.get("workspace_id"), str) and recovery["workspace_id"].strip():
            stored_balance = record_balance_snapshot(
                workspace_id=recovery["workspace_id"],
                amount=recovery["current_balance"]["amount"],
                unit=recovery["current_balance"]["unit"],
                agent_id=args.agent_id,
                source="structured_402",
                estimated=False,
                message=recovery.get("message"),
                required_amount=recovery["required_balance"]["amount"],
                reference={"error_code": "insufficient_balance"},
            )
        if args.json:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "status": status,
                        "provider": provider,
                        "labels": labels or {},
                        "api_key_source": api_key_source,
                        "response": payload,
                        **({"stream_events": stream_events} if stream_events is not None else {}),
                        "message": message,
                        **({"recovery": recovery, "commands": build_recovery_commands(recovery)} if recovery else {}),
                        **({"stored_balance": stored_balance} if stored_balance else {}),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(message, file=sys.stderr)
            if stored_balance:
                print(f"Saved billing snapshot to: {stored_balance['billing_state_path']}", file=sys.stderr)
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "ok": True,
                    "status": status,
                    "provider": provider,
                    "labels": labels or {},
                    "api_key_source": api_key_source,
                    "response_headers": response_headers,
                    "response": payload,
                    **({"stream_events": stream_events} if stream_events is not None else {}),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        if stream_events is not None:
            print(f"Command: {args.command}")
            print(f"Provider override: {provider or '<none; server-side automatic routing>'}")
            print(f"Routing labels: {json.dumps(labels or {}, sort_keys=True)}")
            print("Execution stream:")
            for event in stream_events:
                print(f"- {event['event']}: {json.dumps(event['data'], sort_keys=True)}")
        else:
            print_success(args.command, provider, labels, payload)

    return 0


if __name__ == "__main__":
    sys.exit(main())
