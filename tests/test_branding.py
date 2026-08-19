from pulsearb.branding import COMPANY, PRODUCT, SIGNATURE, resolve_logo_path


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
