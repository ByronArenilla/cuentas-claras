import hashlib

from app.security import (
    generate_invitation_code,
    generate_session_token,
    hash_password,
    hash_token,
    verify_password,
)

PASSWORD = "una-contraseña-larga"


def test_same_password_gives_different_hashes() -> None:
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_password_hash_is_argon2id_and_hides_the_password() -> None:
    password_hash = hash_password(PASSWORD)

    assert password_hash.startswith("$argon2id$")
    assert PASSWORD not in password_hash


def test_verify_accepts_the_right_password() -> None:
    assert verify_password(hash_password(PASSWORD), PASSWORD) is True


def test_verify_rejects_a_wrong_password() -> None:
    assert verify_password(hash_password(PASSWORD), "otra-contraseña-larga") is False


def test_verify_rejects_a_malformed_hash() -> None:
    assert verify_password("no-es-un-hash", PASSWORD) is False


def test_token_hash_is_stable_sha256() -> None:
    token = "token-de-prueba"

    assert hash_token(token) == hash_token(token)
    assert hash_token(token) == hashlib.sha256(token.encode()).hexdigest()
    assert token not in hash_token(token)


def test_session_tokens_do_not_repeat() -> None:
    tokens = {generate_session_token() for _ in range(1000)}

    assert len(tokens) == 1000


def test_invitation_codes_do_not_repeat() -> None:
    codes = {generate_invitation_code() for _ in range(1000)}

    assert len(codes) == 1000


def test_tokens_have_the_planned_entropy() -> None:
    # token_urlsafe(n) codifica n bytes en base64 sin relleno: ~1,33 chars/byte.
    assert len(generate_session_token()) == 43  # 32 bytes = 256 bits
    assert len(generate_invitation_code()) == 22  # 16 bytes = 128 bits
