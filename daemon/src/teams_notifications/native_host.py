#!/usr/bin/env python3
"""Bridges Chrome extension <-> daemon Unix socket."""

import json
import os
import select
import socket
import struct
import sys

SOCKET_PATH = "/run/user/{}/teams-notifications.sock".format(os.getuid())


def read_chrome_message() -> bytes | None:
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) < 4:
        return None
    length = struct.unpack("<I", raw_length)[0]
    if length == 0:
        return b"{}"
    raw = sys.stdin.buffer.read(length)
    if len(raw) < length:
        return None
    return raw


def write_chrome_message(data: bytes) -> None:
    sys.stdout.buffer.write(struct.pack("<I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def recv_exact(sock: socket.socket, n: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


def main():
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(SOCKET_PATH)
    except (FileNotFoundError, ConnectionRefusedError) as e:
        write_chrome_message(
            json.dumps({"error": f"Cannot connect to daemon: {e}"}).encode()
        )
        sys.exit(1)

    stdin_fd = sys.stdin.buffer.fileno()
    sock_fd = sock.fileno()

    try:
        while True:
            readable, _, _ = select.select([stdin_fd, sock_fd], [], [])

            if stdin_fd in readable:
                msg = read_chrome_message()
                if msg is None:
                    break
                sock.sendall(struct.pack("<I", len(msg)) + msg)

            if sock_fd in readable:
                raw_len = recv_exact(sock, 4)
                if raw_len is None:
                    break
                length = struct.unpack("<I", raw_len)[0]
                raw_msg = recv_exact(sock, length)
                if raw_msg is None:
                    break
                write_chrome_message(raw_msg)
    finally:
        sock.close()


if __name__ == "__main__":
    main()
