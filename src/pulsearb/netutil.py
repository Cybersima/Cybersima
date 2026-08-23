from __future__ import annotations

import socket


def lan_hosts() -> list[str]:
    """IPv4 addresses other computers on this Wi-Fi can use to reach this PC."""
    found: list[str] = []
    seen: set[str] = set()

    def add(host: str | None) -> None:
        text = (host or "").strip()
        if not text or text in seen:
            return
        if ":" in text or text.startswith("127.") or text.startswith("169.254."):
            return
        if text.startswith("0.") or text in {"255.255.255.255"}:
            return
        seen.add(text)
        found.append(text)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.3)
        sock.connect(("8.8.8.8", 80))
        add(sock.getsockname()[0])
        sock.close()
    except OSError:
        pass
    try:
        add(socket.gethostbyname(socket.gethostname()))
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            add(info[4][0])
    except OSError:
        pass
    return found


def lan_urls(port: int) -> list[str]:
    return [f"http://{host}:{int(port)}" for host in lan_hosts()]


def port_is_free(host: str, port: int) -> bool:
    """True when nothing is accepting connections on host:port."""
    check_host = "127.0.0.1" if host in {"0.0.0.0", "::", ""} else host
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.3)
    try:
        sock.connect((check_host, port))
    except OSError:
        return True
    finally:
        sock.close()
    return False


def choose_port(host: str, preferred: int, attempts: int = 25) -> int:
    """Return preferred port, or the next free one."""
    for port in range(preferred, preferred + attempts):
        if port_is_free(host, port):
            return port
    raise OSError(
        f"No free port found from {preferred} to {preferred + attempts - 1}. "
        "Close the other CyberSym SecureTrade window, or pass --port."
    )
