from anthology.api.openapi import openapi_document


def test_openapi_document_lists_the_api() -> None:
    document = openapi_document()

    assert document["openapi"].startswith("3.")
    assert "/api/v1/auth/login" in document["paths"]
    assert "TokenResponse" in document["components"]["schemas"]
