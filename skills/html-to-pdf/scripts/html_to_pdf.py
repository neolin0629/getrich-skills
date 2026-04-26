#!/usr/bin/env python3
"""Render HTML or a URL to PDF through Chrome DevTools without Python deps."""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


PAGE_FORMATS: dict[str, tuple[float, float]] = {
    "letter": (8.5, 11.0),
    "legal": (8.5, 14.0),
    "tabloid": (11.0, 17.0),
    "ledger": (17.0, 11.0),
    "a0": (33.1102, 46.811),
    "a1": (23.3858, 33.1102),
    "a2": (16.5354, 23.3858),
    "a3": (11.6929, 16.5354),
    "a4": (8.2677, 11.6929),
    "a5": (5.8268, 8.2677),
    "a6": (4.1339, 5.8268),
}


class CdpError(RuntimeError):
    """Raised when Chrome DevTools returns an error."""


class WebSocket:
    def __init__(self, url: str, timeout: float) -> None:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"ws", "wss"} or not parsed.hostname or not parsed.port:
            raise ValueError(f"Unsupported websocket URL: {url}")
        self._sock = socket.create_connection((parsed.hostname, parsed.port), timeout=timeout)
        if parsed.scheme == "wss":
            self._sock = ssl.create_default_context().wrap_socket(self._sock, server_hostname=parsed.hostname)
        self._sock.settimeout(timeout)
        self._handshake(parsed)

    def _handshake(self, parsed: urllib.parse.ParseResult) -> None:
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        path = parsed.path or "/"
        if parsed.query:
            path += f"?{parsed.query}"
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self._sock.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self._sock.recv(4096)
            if not chunk:
                break
            response += chunk
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise ConnectionError(f"WebSocket handshake failed: {response[:200]!r}")

    def send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        header = bytearray([0x81])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = secrets.token_bytes(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self._sock.sendall(bytes(header) + masked)

    def recv_text(self) -> str:
        chunks: list[bytes] = []
        while True:
            first = self._read_exact(2)
            opcode = first[0] & 0x0F
            masked = bool(first[1] & 0x80)
            length = first[1] & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else b""
            payload = self._read_exact(length) if length else b""
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 0x8:
                raise ConnectionError("WebSocket closed by browser")
            if opcode == 0x9:
                self._send_pong(payload)
                continue
            if opcode in {0x1, 0x0}:
                chunks.append(payload)
                if first[0] & 0x80:
                    return b"".join(chunks).decode("utf-8")

    def _send_pong(self, payload: bytes) -> None:
        header = bytearray([0x8A, 0x80 | len(payload)])
        mask = secrets.token_bytes(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self._sock.sendall(bytes(header) + masked)

    def _read_exact(self, length: int) -> bytes:
        data = b""
        while len(data) < length:
            chunk = self._sock.recv(length - len(data))
            if not chunk:
                raise ConnectionError("Unexpected EOF from WebSocket")
            data += chunk
        return data

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


class CdpClient:
    def __init__(self, websocket_url: str, timeout: float) -> None:
        self._ws = WebSocket(websocket_url, timeout)
        self._next_id = 1
        self.events: list[dict[str, Any]] = []

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        message_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {"id": message_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._ws.send_text(json.dumps(payload, separators=(",", ":")))
        while True:
            message = json.loads(self._ws.recv_text())
            if "id" not in message:
                self.events.append(message)
                continue
            if message["id"] != message_id:
                continue
            if "error" in message:
                error = message["error"]
                raise CdpError(f"{method} failed: {error.get('message', error)}")
            return message.get("result", {})

    def wait_for_event(self, method: str, timeout: float) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for index, event in enumerate(self.events):
                if event.get("method") == method:
                    return self.events.pop(index)
            try:
                message = json.loads(self._ws.recv_text())
            except socket.timeout:
                continue
            if "id" not in message:
                if message.get("method") == method:
                    return message
                self.events.append(message)
        raise TimeoutError(f"Timed out waiting for {method}")

    def close(self) -> None:
        self._ws.close()


def find_browser() -> str:
    env_path = os.environ.get("CHROME_PATH") or os.environ.get("BROWSER_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    candidates = [
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
        "msedge",
        "microsoft-edge",
        "brave-browser",
        "brave",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ]
    for candidate in candidates:
        path = shutil.which(candidate) if "/" not in candidate else candidate
        if path and Path(path).exists():
            return path
    raise SystemExit("Chrome/Chromium not found. Install a browser or set CHROME_PATH=/path/to/browser.")


def input_to_url(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme in {"http", "https", "file"}:
        return value
    path = Path(value).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"Input HTML not found: {path}")
    return path.as_uri()


def default_output_path(input_value: str) -> Path:
    parsed = urllib.parse.urlparse(input_value)
    if parsed.scheme in {"http", "https"}:
        name = Path(parsed.path).stem or "page"
        return Path.cwd() / f"{name}.pdf"
    path = Path(input_value).expanduser()
    if path.suffix.lower() == ".html" or path.suffix.lower() == ".htm":
        return path.with_suffix(".pdf").resolve()
    return path.resolve().with_suffix(".pdf")


def parse_length(value: str) -> float:
    text = value.strip().lower()
    units = {
        "in": 1.0,
        "mm": 1.0 / 25.4,
        "cm": 1.0 / 2.54,
        "px": 1.0 / 96.0,
    }
    for unit, factor in units.items():
        if text.endswith(unit):
            return float(text[: -len(unit)].strip()) * factor
    return float(text)


def page_size(format_name: str, landscape: bool) -> tuple[float, float]:
    key = format_name.lower()
    if key not in PAGE_FORMATS:
        available = ", ".join(sorted(name.upper() for name in PAGE_FORMATS))
        raise SystemExit(f"Unsupported page format: {format_name}. Available: {available}")
    width, height = PAGE_FORMATS[key]
    if landscape:
        return max(width, height), min(width, height)
    return min(width, height), max(width, height)


def wait_for_devtools_port(user_data_dir: Path, process: subprocess.Popen[bytes], timeout: float) -> int:
    active_port = user_data_dir / "DevToolsActivePort"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
            raise SystemExit(f"Browser exited before DevTools started.\n{stderr.strip()}")
        if active_port.exists():
            lines = active_port.read_text(encoding="utf-8").splitlines()
            if lines:
                return int(lines[0])
        time.sleep(0.05)
    raise TimeoutError("Timed out waiting for Chrome DevTools port")


def create_tab(port: int, timeout: float) -> str:
    request = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["webSocketDebuggerUrl"]


def render_pdf(args: argparse.Namespace) -> Path:
    browser = find_browser()
    source_url = input_to_url(args.input)
    output = Path(args.output).expanduser().resolve() if args.output else default_output_path(args.input)
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="html-to-pdf-") as temp_dir:
        user_data_dir = Path(temp_dir) / "profile"
        command = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-extensions",
            "--allow-file-access-from-files",
            f"--user-data-dir={user_data_dir}",
            "--remote-debugging-port=0",
            "about:blank",
        ]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        client: CdpClient | None = None
        try:
            port = wait_for_devtools_port(user_data_dir, process, args.timeout)
            client = CdpClient(create_tab(port, args.timeout), args.timeout)
            client.call("Page.enable")
            client.call("Runtime.enable")
            client.call("Emulation.setEmulatedMedia", {"media": args.media})
            client.call("Page.navigate", {"url": source_url})
            client.wait_for_event("Page.loadEventFired", args.timeout)
            if args.wait_ms > 0:
                time.sleep(args.wait_ms / 1000)

            width, height = page_size(args.format, args.landscape)
            margin_values = {
                "top": parse_length(args.margin_top or args.margin),
                "right": parse_length(args.margin_right or args.margin),
                "bottom": parse_length(args.margin_bottom or args.margin),
                "left": parse_length(args.margin_left or args.margin),
            }
            result = client.call(
                "Page.printToPDF",
                {
                    "landscape": args.landscape,
                    "printBackground": not args.no_background,
                    "preferCSSPageSize": args.prefer_css_page_size,
                    "paperWidth": width,
                    "paperHeight": height,
                    "marginTop": margin_values["top"],
                    "marginRight": margin_values["right"],
                    "marginBottom": margin_values["bottom"],
                    "marginLeft": margin_values["left"],
                    "scale": args.scale,
                    "displayHeaderFooter": False,
                },
            )
            output.write_bytes(base64.b64decode(result["data"]))
        finally:
            if client is not None:
                client.close()
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
    return output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render local/remote HTML to PDF using Chrome DevTools.")
    parser.add_argument("input", help="HTML file path, file:// URL, or http(s) URL")
    parser.add_argument("-o", "--output", help="Output PDF path. Defaults to input stem with .pdf")
    parser.add_argument("--format", default="A4", help="Paper format: A4, Letter, Legal, A3, etc. Default: A4")
    parser.add_argument("--landscape", action="store_true", help="Use landscape orientation")
    parser.add_argument(
        "--margin",
        default="0",
        help=(
            "Chrome print margin for all sides. Default: 0, so page backgrounds can bleed "
            "to the PDF edge. Use CSS @page/body padding for document whitespace."
        ),
    )
    parser.add_argument("--margin-top", help="Top margin override")
    parser.add_argument("--margin-right", help="Right margin override")
    parser.add_argument("--margin-bottom", help="Bottom margin override")
    parser.add_argument("--margin-left", help="Left margin override")
    parser.add_argument("--media", choices=["print", "screen"], default="print", help="CSS media to emulate")
    parser.add_argument("--prefer-css-page-size", action="store_true", help="Prefer CSS @page size over --format")
    parser.add_argument("--no-background", action="store_true", help="Disable printing backgrounds")
    parser.add_argument("--scale", type=float, default=1.0, help="Print scale from 0.1 to 2.0")
    parser.add_argument("--wait-ms", type=int, default=300, help="Extra wait after load for fonts/charts")
    parser.add_argument("--timeout", type=float, default=30.0, help="Browser operation timeout in seconds")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not 0.1 <= args.scale <= 2.0:
        parser.error("--scale must be between 0.1 and 2.0")
    output = render_pdf(args)
    size = output.stat().st_size if output.exists() else 0
    if size <= 0:
        raise SystemExit(f"PDF was not created correctly: {output}")
    print(f"[OK] PDF saved: {output} ({size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
