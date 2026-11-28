import pytest
from app.modules.lexicon.normalization import normalize_lexeme_text


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
def test_normalize_lexeme_text(raw: str, expected: str) -> None:
    assert normalize_lexeme_text(raw) == expected


def test_normalization_is_idempotent() -> None:
    once = normalize_lexeme_text("  Don\u2019t   Stop ")

    assert normalize_lexeme_text(once) == once
