#!/usr/bin/env python3
"""Claude Code hook entry point — relays Notification/Stop events to the
Claude Desktop Buddy daemon over its local Unix socket.

Wired via ~/.claude/settings.json "hooks" config, invoked with the hook's
JSON payload on stdin (see https://docs.claude.com/en/docs/claude-code/hooks
for the schema). Deliberately best-effort and silent: the daemon may not be
running (board unplugged, daemon not started) and that must never surface as
a hook failure or block the actual Claude Code turn — so every failure path
here exits 0 after printing a one-line note to stderr, never non-zero.
"""

import json
import os
import socket
import sys

SOCKET_PATH = os.path.expanduser("~/.claude_desktop_buddy.sock")
CONNECT_TIMEOUT_S = 2


def build_message(payload: dict) -> str:
    event = payload.get("hook_event_name", "")
    if event == "Notification":
        return payload.get("message", "ClaudeCode notification")
    if event == "Stop":
        cwd = payload.get("cwd", "")
        project = os.path.basename(cwd.rstrip("/")) if cwd else ""
        return f"ClaudeCode stopped ({project})" if project else "ClaudeCode stopped"
    return event or "ClaudeCode event"


def relay(message: str) -> None:
    if not os.path.exists(SOCKET_PATH):
        print("[hook_relay] daemon not running, skipping", file=sys.stderr)
        return
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(CONNECT_TIMEOUT_S)
    try:
        s.connect(SOCKET_PATH)
        s.sendall(message.encode("utf-8") + b"\n")
        s.recv(16)  # drain the ok/err reply; not acted on here
    except OSError as e:
        print(f"[hook_relay] relay failed: {e}", file=sys.stderr)
    finally:
        s.close()


def main() -> None:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError) as e:
        print(f"[hook_relay] bad stdin payload: {e}", file=sys.stderr)
        payload = {}

    message = build_message(payload)
    relay(message)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never let a hook bug block the agent turn
        print(f"[hook_relay] unexpected error: {e}", file=sys.stderr)
    sys.exit(0)
