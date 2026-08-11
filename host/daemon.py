#!/usr/bin/env python3
"""Claude Desktop Buddy — MVP host daemon.

Maintains a BLE connection to the M5StickC Plus running
claude_desktop_buddy.ino, and forwards any line received on a local Unix
socket to the device's PROMPT_CHAR_UUID characteristic.

Notify-only MVP: no decision is read back from the device. Button presses
on the device just clear its local display/queue.

Run:
    python3 daemon.py

Send a message from another process/script (see send.py for a CLI wrapper):
    import socket
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(SOCKET_PATH)
    s.sendall(b"hello\n")
"""

import asyncio
import os
import signal

from bleak import BleakClient, BleakScanner

DEVICE_NAME = "ClaudeBuddy"
SERVICE_UUID = "58f54036-4176-47fe-890f-9f3abdadd857"
PROMPT_CHAR_UUID = "997b42ca-70d2-47be-bb6a-9943bd41f24b"

# Keep well under the firmware's negotiated MTU (185) so a single BLE write
# always fits, even against a central/stack that doesn't renegotiate MTU.
MAX_MESSAGE_BYTES = 160

SOCKET_PATH = os.path.expanduser("~/.claude_desktop_buddy.sock")

RECONNECT_DELAY_S = 5
SCAN_TIMEOUT_S = 10


class BuddyLink:
    def __init__(self):
        self.client: BleakClient | None = None
        self.connected = asyncio.Event()

    async def run_forever(self):
        while True:
            try:
                await self._connect_and_hold()
            except Exception as e:
                print(f"[buddy] connection error: {e}")
            self.connected.clear()
            self.client = None
            print(f"[buddy] reconnecting in {RECONNECT_DELAY_S}s...")
            await asyncio.sleep(RECONNECT_DELAY_S)

    async def _connect_and_hold(self):
        print(f"[buddy] scanning for '{DEVICE_NAME}'...")
        device = await BleakScanner.find_device_by_name(
            DEVICE_NAME, timeout=SCAN_TIMEOUT_S
        )
        if device is None:
            print(f"[buddy] '{DEVICE_NAME}' not found, will retry")
            return

        print(f"[buddy] found {device.address}, connecting...")
        # Hold the connection open; bleak drops out of this block on
        # disconnect, which sends us back to the retry loop above.
        disconnect_event = asyncio.Event()
        async with BleakClient(
            device, disconnected_callback=lambda _: disconnect_event.set()
        ) as client:
            self.client = client
            self.connected.set()
            print("[buddy] connected")
            await disconnect_event.wait()
        print("[buddy] disconnected")

    async def send(self, text: str) -> bool:
        if not self.client or not self.connected.is_set():
            print("[buddy] send failed: not connected")
            return False
        payload = text.encode("utf-8")[:MAX_MESSAGE_BYTES]
        try:
            await self.client.write_gatt_char(
                PROMPT_CHAR_UUID, payload, response=False
            )
            return True
        except Exception as e:
            print(f"[buddy] write failed: {e}")
            return False


async def handle_client(reader, writer, link: BuddyLink):
    try:
        while True:
            line = await reader.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            ok = await link.send(text)
            writer.write(b"ok\n" if ok else b"err\n")
            await writer.drain()
    finally:
        writer.close()


async def run_socket_server(link: BuddyLink):
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)

    server = await asyncio.start_unix_server(
        lambda r, w: handle_client(r, w, link), path=SOCKET_PATH
    )
    print(f"[buddy] listening on {SOCKET_PATH}")
    async with server:
        await server.serve_forever()


async def main():
    link = BuddyLink()

    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    ble_task = asyncio.create_task(link.run_forever())
    socket_task = asyncio.create_task(run_socket_server(link))

    await stop.wait()
    ble_task.cancel()
    socket_task.cancel()
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)


if __name__ == "__main__":
    asyncio.run(main())
