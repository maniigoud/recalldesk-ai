"""Unit tests for password hashing and JWT handling (no database required)."""

from __future__ import annotations

import pytest

from app.core.errors import AuthenticationError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("DemoPassword123!")
    second = hash_password("DemoPassword123!")

    assert first != "DemoPassword123!"
    assert first != second
    assert verify_password("DemoPassword123!", first)
    assert not verify_password("wrong-password", first)


def test_verify_password_handles_garbage_hash():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_access_token_round_trip():
    token = create_access_token(subject="42", role="agent", organization_id=7)
    payload = decode_access_token(token)

    assert payload["sub"] == "42"
    assert payload["role"] == "agent"
    assert payload["organization_id"] == 7
    assert payload["type"] == "access"


def test_invalid_token_is_rejected():
    with pytest.raises(AuthenticationError):
        decode_access_token("not-a-jwt")


def test_token_signed_with_another_secret_is_rejected():
    import jwt

    forged = jwt.encode({"sub": "1", "exp": 9999999999}, "other-secret", algorithm="HS256")
    with pytest.raises(AuthenticationError):
        decode_access_token(forged)
