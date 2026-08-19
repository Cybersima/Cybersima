from __future__ import annotations

import socket


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
