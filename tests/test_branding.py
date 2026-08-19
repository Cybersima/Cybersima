from securetrade.branding import COMPANY, GUARDIAN_NAME, PRODUCT, SIGNATURE, TAGLINE, VERSION


def test_company_and_product_names() -> None:
    assert COMPANY == "CyberSym"
    assert PRODUCT == "CyberSym SecureTrade 2"
    assert SIGNATURE == "A CyberSym product"
    assert "Guardian" in GUARDIAN_NAME
    assert VERSION.startswith("2.")
    assert "walk away" in TAGLINE.lower()
