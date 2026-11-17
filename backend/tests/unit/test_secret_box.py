from cookfully.infrastructure.secret_box import SecretBox


def test_round_trip_and_ciphertext_hides_plaintext() -> None:
    box = SecretBox("a-long-enough-secret-key-for-tests-0000")
    token = box.encrypt("sk-or-plain")
    assert "sk-or-plain" not in token
    assert box.decrypt(token) == "sk-or-plain"


def test_encryption_is_randomized() -> None:
    box = SecretBox("secret-a" * 5)
    assert box.encrypt("same") != box.encrypt("same")


def test_wrong_secret_or_garbage_decrypts_to_none() -> None:
    token = SecretBox("secret-a" * 5).encrypt("value")
    assert SecretBox("secret-b" * 5).decrypt(token) is None
    assert SecretBox("secret-a" * 5).decrypt("garbage") is None
    assert SecretBox("secret-a" * 5).decrypt("") is None
