import socket

from pulsearb.netutil import choose_port, port_is_free


def test_choose_port_skips_busy_listener() -> None:
    busy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    busy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    busy.bind(("127.0.0.1", 0))
    busy.listen(1)
    port = busy.getsockname()[1]
    try:
        assert not port_is_free("127.0.0.1", port)
        next_port = choose_port("127.0.0.1", port)
        assert next_port != port
        assert next_port > port
        assert port_is_free("127.0.0.1", next_port)
    finally:
        busy.close()
