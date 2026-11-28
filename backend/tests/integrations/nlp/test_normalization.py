import pytest
from app.integrations.nlp.normalization import normalize_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Bank", "bank"),
        ("  look   forward\tto \n", "look forward to"),
        ("don\u2019t", "don't"),
        ("rock \u2018n\u2019 roll", "rock 'n' roll"),
        ("café", "café"),
        ("", ""),
    ],
)
def test_normalize_text(raw: str, expected: str) -> None:
    assert normalize_text(raw) == expected


def test_normalization_is_idempotent() -> None:
    once = normalize_text("  Don\u2019t   Stop ")

    assert normalize_text(once) == once
