"""Run an OLED firmware ACK smoke test over the JSON serial protocol."""

from __future__ import annotations

import argparse
import json
import os
import select
import sys
import time
from typing import BinaryIO, Optional, Sequence, Union

from jks import display as jks_display


DEFAULT_PORT = "/dev/cu.usbmodem5B900048301"
DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 2.5

_COMMANDS = [
    ({"cmd": "probe"}, "probe"),
    ({"cmd": "emotion", "name": "happy", "text": "SMOKE OK"}, "happy"),
    ({"cmd": "text", "text": "JKS SMOKE"}, "text"),
    ({"cmd": "clear"}, "clear"),
]


def _write_frame(port: BinaryIO, payload: dict[str, object]) -> None:
    frame = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    port.write(frame + b"\n")
    port.flush()


def _readline(port: BinaryIO, timeout: float) -> Union[bytes, str]:
    fd = _port_fileno(port)
    if fd is not None:
        return _readline_fd(fd, timeout)

    try:
        ready, _, _ = select.select([port], [], [], timeout)
    except (OSError, TypeError, ValueError):
        ready = [port]
    if not ready:
        return b""
    return port.readline()


def _port_fileno(port: BinaryIO) -> Optional[int]:
    try:
        return port.fileno()
    except (AttributeError, OSError, ValueError):
        return None


def _readline_fd(fd: int, timeout: float) -> bytes:
    deadline = time.monotonic() + max(timeout, 0.0)
    chunks = bytearray()
    while True:
        remaining = max(deadline - time.monotonic(), 0.0)
        try:
            ready, _, _ = select.select([fd], [], [], remaining)
        except (OSError, ValueError):
            return bytes(chunks)
        if not ready:
            return bytes(chunks)
        try:
            chunk = os.read(fd, 1)
        except BlockingIOError:
            continue
        except OSError:
            return bytes(chunks)
        if not chunk:
            return bytes(chunks)
        chunks.extend(chunk)
        if chunk == b"\n" or time.monotonic() >= deadline:
            return bytes(chunks)


def _drain_input(port: BinaryIO, timeout: float = 0.05) -> None:
    deadline = time.monotonic() + max(timeout, 0.0)
    while True:
        remaining = max(deadline - time.monotonic(), 0.0)
        if remaining <= 0:
            return
        if not _readline(port, remaining):
            return


def _read_ack(
    port: BinaryIO,
    timeout: float,
    errors: list[dict[str, str]],
    expected_detail: str,
) -> Optional[dict[str, object]]:
    deadline = time.monotonic() + max(timeout, 0.0)
    pending_errors: list[dict[str, str]] = []
    while True:
        remaining = max(deadline - time.monotonic(), 0.0)
        line = _readline(port, remaining)
        if not line:
            errors.extend(pending_errors)
            return None
        if isinstance(line, bytes):
            try:
                text = line.decode("utf-8")
            except UnicodeDecodeError as exc:
                pending_errors.append({"error": "decode", "message": str(exc)})
                continue
        else:
            text = line

        text = text.strip()
        if not text:
            continue
        try:
            ack = json.loads(text)
        except json.JSONDecodeError as exc:
            pending_errors.append({"error": "json", "line": text, "message": str(exc)})
            continue
        if isinstance(ack, dict):
            if _ack_detail(ack) == expected_detail:
                return ack
            if time.monotonic() >= deadline:
                errors.extend(pending_errors)
                return None
            continue
        pending_errors.append({"error": "ack_type", "line": text})
        if time.monotonic() >= deadline:
            errors.extend(pending_errors)
            return None


def _ack_detail(ack: dict[str, object]) -> str:
    detail = ack.get("detail", ack.get("cmd", ""))
    return str(detail)


def _ack_is_ok(ack: dict[str, object]) -> bool:
    status = ack.get("status")
    if status is not None and status != "ok":
        return False
    ok = ack.get("ok")
    return ok is not False


def _missing_details(expected: list[str], actual: list[str]) -> list[str]:
    remaining = list(actual)
    missing = []
    for detail in expected:
        try:
            remaining.remove(detail)
        except ValueError:
            missing.append(detail)
    return missing


def _run_on_port(port: BinaryIO, timeout: float, drain_stale_input: bool = False) -> dict[str, object]:
    acks: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    expected_details = [detail for _, detail in _COMMANDS]

    for payload, expected_detail in _COMMANDS:
        if drain_stale_input:
            _drain_input(port)
        _write_frame(port, payload)
        ack = _read_ack(port, timeout, errors, expected_detail)
        if ack is not None:
            acks.append(ack)

    details = [_ack_detail(ack) for ack in acks]
    missing = _missing_details(expected_details, details)
    status_errors = [ack for ack in acks if not _ack_is_ok(ack)]
    return {
        "ok": not missing and not errors and not status_errors,
        "acks": acks,
        "details": details,
        "missing": missing,
        "errors": errors,
    }


def run_oled_smoke(
    port: Optional[BinaryIO] = None,
    port_path: str = DEFAULT_PORT,
    baud: int = DEFAULT_BAUD,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, object]:
    if port is not None:
        return _run_on_port(port, timeout, drain_stale_input=getattr(port, "drain_stale_input", False))

    with jks_display.open_serial_output(port_path, baud) as opened_port:
        drain_stale_input = getattr(opened_port, "drain_stale_input", False) or _port_fileno(opened_port) is not None
        return _run_on_port(opened_port, timeout, drain_stale_input=drain_stale_input)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run MicroPython OLED firmware ACK smoke over serial.")
    parser.add_argument("--port", default=DEFAULT_PORT, help=f"Serial port path. Default: {DEFAULT_PORT}.")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help=f"Serial baud. Default: {DEFAULT_BAUD}.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"ACK timeout per command in seconds. Default: {DEFAULT_TIMEOUT}.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None, stdout=sys.stdout) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = run_oled_smoke(port_path=args.port, baud=args.baud, timeout=args.timeout)
    except Exception as exc:
        summary = {
            "ok": False,
            "acks": [],
            "details": [],
            "missing": [detail for _, detail in _COMMANDS],
            "errors": [{"error": "open_serial", "message": str(exc)}],
        }
    stdout.write(json.dumps(summary, ensure_ascii=False, separators=(",", ":")) + "\n")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
