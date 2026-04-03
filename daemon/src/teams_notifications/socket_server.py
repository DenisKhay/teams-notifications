from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
from pathlib import Path
from typing import Awaitable, Callable

log = logging.getLogger(__name__)


def get_socket_path() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return Path(runtime_dir) / "teams-notifications.sock"


class SocketServer:
    def __init__(self, on_message: Callable[[dict], Awaitable[None]]):
        self._on_message = on_message
        self._server: asyncio.AbstractServer | None = None
        self._socket_path = get_socket_path()

    async def start(self) -> None:
        if self._socket_path.exists():
            self._socket_path.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self._socket_path),
        )
        os.chmod(self._socket_path, 0o600)
        log.info("Socket server listening on %s", self._socket_path)

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        log.info("Native host connected")
        try:
            while True:
                raw_len = await reader.readexactly(4)
                length = struct.unpack("<I", raw_len)[0]
                if length == 0:
                    continue
                if length > 1_048_576:
                    log.warning("Message too large (%d bytes), dropping", length)
                    await reader.readexactly(length)
                    continue
                raw_msg = await reader.readexactly(length)
                msg = json.loads(raw_msg.decode("utf-8"))
                log.debug("Received from native host: %s", msg)
                await self._on_message(msg)

                ack = json.dumps({"type": "ack"}).encode("utf-8")
                writer.write(struct.pack("<I", len(ack)) + ack)
                await writer.drain()
        except asyncio.IncompleteReadError:
            log.info("Native host disconnected")
        except Exception:
            log.exception("Error handling native host connection")
        finally:
            writer.close()
            await writer.wait_closed()

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        if self._socket_path.exists():
            self._socket_path.unlink()
