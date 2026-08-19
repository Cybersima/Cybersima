from securetrade.cli import build_parser


def test_cli_commands_exist() -> None:
    parser = build_parser()
    args = parser.parse_args(["engine", "--demo", "--port", "8000", "--no-browser"])
    assert args.command == "engine"
    assert args.demo is True
    assert args.port == 8000
    assert args.no_browser is True
