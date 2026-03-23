#!/usr/bin/env python3
"""Authenticated claw-federation platform requests with routing hints."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from openclaw_platform_auth import DEFAULT_AGENT_ID, DEFAULT_PROFILE_ID, resolve_platform_api_key


ERROR_HELP = {
    "missing_api_key": "Missing platform API key. Export CLAW_FEDERATION_PLATFORM_API_KEY first.",
    "invalid_api_key": "The platform API key was rejected. Re-bootstrap a fresh key and retry.",
    "api_key_inactive": "The platform API key is no longer active. Bootstrap a replacement key.",
    "workspace_missing": "The API key resolved, but its workspace no longer exists on the server.",
    "account_missing": "The API key resolved, but its owning account no longer exists on the server.",
    "missing_federation_provider": "No explicit provider was supplied. Set --provider or CLAW_FEDERATION_DEFAULT_PROVIDER_ID.",
    "invalid_routing_labels": "Routing labels were invalid. Use repeated --label key=value flags or valid JSON in CLAW_FEDERATION_DEFAULT_ROUTING_LABELS.",
    "provider_unavailable": "The selected provider is not currently connected.",
    "provider_label_mismatch": "The selected provider does not satisfy the requested routing hints.",
    "llm_api_not_available": "The selected provider is connected, but it does not expose the responses API.",
    "llm_model_not_allowed": "The requested model is not allowed by the selected provider.",
    "skill_not_available": "No connected provider currently exposes that skill.",
    "skill_not_available_on_provider": "That provider does not expose the requested skill.",
    "invalid_request": "The request payload did not match the server contract.",
}


def parse_args() -> argparse.Namespace:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--server-url",
        default=os.environ.get("CLAW_FEDERATION_SERVER_URL", "").strip(),
        help="Base URL for claw-federation-server. Defaults to CLAW_FEDERATION_SERVER_URL.",
    )
    common.add_argument(
        "--api-key",
        default=os.environ.get("CLAW_FEDERATION_PLATFORM_API_KEY", "").strip(),
        help="Platform API key. Defaults to CLAW_FEDERATION_PLATFORM_API_KEY, then OpenClaw auth-profiles.json.",
    )
    common.add_argument(
        "--provider",
        default=os.environ.get("CLAW_FEDERATION_DEFAULT_PROVIDER_ID", "").strip(),
        help="Explicit provider target. Defaults to CLAW_FEDERATION_DEFAULT_PROVIDER_ID.",
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
        description="Send authenticated claw-federation platform requests with provider selection and routing hints.",
        parents=[common],
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    responses = subparsers.add_parser(
        "responses",
        help="Send a /v1/responses request.",
        parents=[common],
    )
    responses.add_argument(
        "--body-json",
        help="Raw JSON object payload for /v1/responses.",
    )
    responses.add_argument(
        "--body-file",
        help="Path to a JSON file containing the /v1/responses payload.",
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
        "or bootstrap with --store so the key is saved into OpenClaw auth-profiles.json."
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
    env_raw = os.environ.get("CLAW_FEDERATION_DEFAULT_ROUTING_LABELS", "").strip()
    if env_raw:
        env_labels = load_json_object(env_raw, source="CLAW_FEDERATION_DEFAULT_ROUTING_LABELS")
        for key, value in env_labels.items():
            if not isinstance(key, str) or not isinstance(value, str) or not key or not value.strip():
                raise SystemExit(
                    "CLAW_FEDERATION_DEFAULT_ROUTING_LABELS must be a JSON object of non-empty string values."
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
) -> tuple[int, dict[str, Any] | str, dict[str, str]]:
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
            payload_out: dict[str, Any] | str
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
        raise SystemExit(f"Request failed for {method} {url}: {error.reason}") from error


def explain_error(code: int, payload: dict[str, Any] | str, provider: str | None, labels: dict[str, str] | None) -> str:
    if isinstance(payload, dict):
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


def print_success(command: str, provider: str, labels: dict[str, str] | None, payload: dict[str, Any] | str) -> None:
    print(f"Command: {command}")
    print(f"Provider: {provider}")
    if labels:
        print(f"Routing labels: {json.dumps(labels, sort_keys=True)}")
    else:
        print("Routing labels: <none>")
    print("Response:")
    if isinstance(payload, str):
        print(payload)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))


def main() -> int:
    args = parse_args()
    server_url = require_non_empty(
        args.server_url,
        "Missing server URL. Set CLAW_FEDERATION_SERVER_URL or pass --server-url.",
    ).rstrip("/")
    api_key, api_key_source = resolve_api_key_or_exit(args.api_key, args.profile_id, args.agent_id)
    provider = require_non_empty(
        args.provider,
        "Missing provider. Pass --provider or set CLAW_FEDERATION_DEFAULT_PROVIDER_ID.",
    )
    labels = resolve_labels(args.label)

    if args.command == "responses":
        body = load_json_object_from_option(args.body_json, args.body_file, source_name="body")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "x-federation-provider": provider,
        }
        if labels:
            headers["x-federation-labels"] = json.dumps(labels, sort_keys=True)
        status, payload, response_headers = request(
            url=f"{server_url}/v1/responses",
            method="POST",
            headers=headers,
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
            "provider_id": provider,
        }
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
    else:
        raise SystemExit(f"Unsupported command: {args.command}")

    if status >= 400:
        message = explain_error(status, payload, provider, labels)
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
                        "message": message,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(message, file=sys.stderr)
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
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print_success(args.command, provider, labels, payload)

    return 0


if __name__ == "__main__":
    sys.exit(main())
