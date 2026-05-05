from app.main import _expand_local_cors_origins


def test_expand_local_cors_origins_adds_loopback_aliases() -> None:
    origins = _expand_local_cors_origins(["http://localhost:5173"])

    assert "http://localhost:5173" in origins
    assert "http://127.0.0.1:5173" in origins
    assert "http://[::1]:5173" in origins


def test_expand_local_cors_origins_preserves_non_local_origins() -> None:
    origins = _expand_local_cors_origins(["https://app.example.com"])

    assert origins == ["https://app.example.com"]
