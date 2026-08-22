import zipfile

from securetrade.cli import build_parser
from securetrade.packager import build_zip, folder_name, zip_name


def test_customer_zip_contains_launchers_and_forex_desk(tmp_path) -> None:
    dest = tmp_path / zip_name()
    built = build_zip(dest)
    assert built.exists()
    assert built.stat().st_size > 10_000
    checksum = dest.with_suffix(".zip.sha256")
    assert checksum.exists()
    with zipfile.ZipFile(built) as zf:
        names = zf.namelist()
    prefix = folder_name()
    for needed in (
        f"{prefix}/start.bat",
        f"{prefix}/start.sh",
        f"{prefix}/start.command",
        f"{prefix}/START_HERE.txt",
        f"{prefix}/HOW_TO_INSTALL.txt",
        f"{prefix}/TERMS.txt",
        f"{prefix}/src/securetrade/engine/forex.py",
        f"{prefix}/src/securetrade/web/templates/download.html",
    ):
        assert needed in names


def test_ensure_installer_publishes_static_copy() -> None:
    from securetrade.packager import ensure_installer, static_zip_path

    ready = ensure_installer()
    assert ready.exists()
    assert ready.stat().st_size > 10_000
    assert static_zip_path().exists()


def test_cli_package_command_exists() -> None:
    parser = build_parser()
    args = parser.parse_args(["package"])
    assert args.command == "package"
