from app.security import hash_password, hash_token, is_valid_email, verify_password


def test_password_hash_round_trip_and_salting():
    stored = hash_password("correct horse")
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong", stored)
    assert hash_password("same") != hash_password("same")  # unique salts


def test_garbage_hash_never_verifies():
    assert not verify_password("x", "plaintext")
    assert not verify_password("x", "md5$00$00")


def test_session_tokens_are_stored_hashed():
    assert hash_token("abc") != "abc" and len(hash_token("abc")) == 64


def test_email_validation():
    assert is_valid_email("a@b.co")
    assert not is_valid_email("a@b")
    assert not is_valid_email("a b@c.d")
