import pytest

from app.pii import scrub_text


def test_scrub_email() -> None:
    out = scrub_text("Email me at student@vinuni.edu.vn")
    assert "student@" not in out
    assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_redacts_cccd() -> None:
    raw = "CCCD 001099012345"
    redacted = scrub_text(raw)
    assert "001099012345" not in redacted
    assert "[REDACTED_CCCD]" in redacted


@pytest.mark.parametrize(
    "card",
    [
        "4111111111111111",
        "4111 1111 1111 1111",
        "4111-1111-1111-1111",
    ],
)
def test_redacts_credit_card(card: str) -> None:
    out = scrub_text(f"Card: {card}")
    assert card not in out
    assert "[REDACTED_CREDIT_CARD]" in out


def test_redacts_multiple_pii_types_in_one_message() -> None:
    raw = (
        "a@b.vn 0901234567 "
        "001099012345 "
        "4111 1111 1111 1111"
    )
    out = scrub_text(raw)
    assert "a@b.vn" not in out
    assert "0901234567" not in out
    assert "001099012345" not in out
    assert "4111 1111 1111 1111" not in out
    assert "[REDACTED_EMAIL]" in out
    assert "[REDACTED_PHONE_VN]" in out
    assert "[REDACTED_CCCD]" in out
    assert "[REDACTED_CREDIT_CARD]" in out

