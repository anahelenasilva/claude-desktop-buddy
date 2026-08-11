# Claude Desktop Buddy (MVP)

Notify-only BLE pager: a Mac daemon sends text to an M5StickC Plus 1.1,
which buzzes, blinks its LED, and shows the message. Button A dismisses /
advances the queue, Button B clears it. No decision is sent back to the
Mac; that's V2, gated on whether Claude Code exposes a way to inject a
remote approval into a pending permission prompt (unverified, not scoped
here).

## Parts

- `firmware/claude_desktop_buddy.ino`: device firmware. Symlinked from
  `~/Documents/Arduino/claude_desktop_buddy/claude_desktop_buddy.ino` so
  Arduino IDE can still open/flash it from the sketchbook location.
  Requires the `M5StickCPlus` and `NimBLE-Arduino` Arduino libraries.
- `host/daemon.py`: Mac-side background process. Scans for the device by
  name (`ClaudeBuddy`), holds a BLE connection, reconnects on drop, and
  listens on a local Unix socket (`~/.claude_desktop_buddy.sock`) for
  messages to relay.
- `host/send.py`: one-line CLI to push a message through the running
  daemon: `python3 send.py "background task finished"`.
- `host/hook_relay.py`: Claude Code hook entry point. Reads a hook's JSON
  payload from stdin and relays it to `daemon.py`'s socket; best-effort,
  always exits 0 so a stopped daemon never blocks an agent turn. Wired
  into `~/.claude/settings.json` under `hooks.Notification` / `hooks.Stop`.

## Setup

1. Flash `claude_desktop_buddy.ino` to the M5StickC Plus (Arduino IDE,
   board = "M5StickC Plus", after installing the two libraries above).
2. `cd host && python3 -m pip install -r requirements.txt`
3. `python3 daemon.py`, leave running. It prints connection state.
4. From anywhere: `python3 host/send.py "hello"`, device should buzz and
   show it within a couple seconds.

## Not in this MVP

- No approve/deny round-trip (V2).
- No message persistence across device reboot (RAM-only 3-slot queue).
- Daemon isn't installed as a LaunchAgent; it's a foreground script for
  now, turn it into a `launchd` plist once the rest is confirmed working.
