from pathlib import Path

from pulsearb.branding import COMPANY, PRODUCT, SIGNATURE, install_logo, resolve_logo_path


def test_company_and_product_names() -> None:
    assert COMPANY == "CyberSym"
    assert PRODUCT == "CyberSym SecureTrade"
    assert SIGNATURE == "A CyberSym product"


def test_custom_logo_in_branding_folder_wins(tmp_path) -> None:
    web = tmp_path / "web" / "static"
    web.mkdir(parents=True)
    (web / "logo.png").write_bytes(b"default")
    branding = tmp_path / "branding"
    branding.mkdir()
    custom = branding / "cybersym-logo.png"
    custom.write_bytes(b"official")
    assert resolve_logo_path(tmp_path / "web", cwd=tmp_path) == custom
    custom.unlink()
    assert resolve_logo_path(tmp_path / "web", cwd=tmp_path) == web / "logo.png"


def test_any_image_in_branding_is_used(tmp_path) -> None:
    web = tmp_path / "web" / "static"
    web.mkdir(parents=True)
    (web / "logo.png").write_bytes(b"default")
    branding = tmp_path / "branding"
    branding.mkdir()
    dropped = branding / "My Crest.png"
    dropped.write_bytes(b"dropped")
    assert resolve_logo_path(tmp_path / "web", cwd=tmp_path) == dropped


def test_install_logo_renames_and_replaces(tmp_path) -> None:
    branding = tmp_path / "branding"
    branding.mkdir()
    (branding / "logo.png").write_bytes(b"old")
    src = tmp_path / "crest.jpg"
    src.write_bytes(b"jpeg-bytes")
    dest = install_logo(src, cwd=tmp_path)
    assert dest == branding / "cybersym-logo.jpg"
    assert dest.read_bytes() == b"jpeg-bytes"
    assert not (branding / "logo.png").exists()
    web = tmp_path / "web" / "static"
    web.mkdir(parents=True)
    (web / "logo.png").write_bytes(b"default")
    assert resolve_logo_path(tmp_path / "web", cwd=tmp_path) == dest


def test_src_layout_branding_found_when_cwd_differs(tmp_path, monkeypatch) -> None:
    repo = tmp_path / "app"
    web = repo / "src" / "pulsearb" / "web"
    (web / "static").mkdir(parents=True)
    (web / "static" / "logo.png").write_bytes(b"default")
    branding = repo / "branding"
    branding.mkdir()
    custom = branding / "cybersym-logo.png"
    custom.write_bytes(b"official")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert resolve_logo_path(web) == custom
