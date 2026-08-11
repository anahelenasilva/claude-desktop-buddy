#!/usr/bin/env python3
"""CLI helper: forward a message to the running daemon.py over its Unix socket.

Usage:
    python3 send.py "background task finished"

Intended as the integration point for hooks/scripts (e.g. a Claude Code
Notification/Stop hook) — call this instead of talking BLE directly.
"""

import os
import socket
import sys

SOCKET_PATH = os.path.expanduser("~/.claude_desktop_buddy.sock")


def main():
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} '<message>'", file=sys.stderr)
        sys.exit(1)

    message = sys.argv[1]

    if not os.path.exists(SOCKET_PATH):
        print("daemon not running (socket not found) — start daemon.py first", file=sys.stderr)
        sys.exit(1)

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(SOCKET_PATH)
        s.sendall(message.encode("utf-8") + b"\n")
        reply = s.recv(16)
        if reply.strip() != b"ok":
            print(f"daemon reported failure: {reply!r}", file=sys.stderr)
            sys.exit(1)
    finally:
        s.close()


if __name__ == "__main__":
    main()
