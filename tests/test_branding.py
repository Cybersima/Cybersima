from pulsearb.branding import COMPANY, PRODUCT, SIGNATURE


def test_company_and_product_names() -> None:
    assert COMPANY == "CyberSym"
    assert PRODUCT == "CyberSym SecureTrade"
    assert SIGNATURE == "A CyberSym product"
