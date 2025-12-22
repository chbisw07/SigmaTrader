from app.services.instruments_sync import _canonicalize_smartapi_symbol


def test_canonicalize_smartapi_symbol_strips_eq_suffix() -> None:
    assert _canonicalize_smartapi_symbol("RPOWER-EQ") == "RPOWER"


def test_canonicalize_smartapi_symbol_strips_be_suffix() -> None:
    assert _canonicalize_smartapi_symbol("SOMETHING-BE") == "SOMETHING"


def test_canonicalize_smartapi_symbol_keeps_plain_symbol() -> None:
    assert _canonicalize_smartapi_symbol("RELIANCE") == "RELIANCE"
