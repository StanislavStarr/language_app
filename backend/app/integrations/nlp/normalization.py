import re
import unicodedata

TYPOGRAPHIC_APOSTROPHES = str.maketrans(
    {"\u2019": "'", "\u2018": "'", "\u02bc": "'", "`": "'", "\u00b4": "'"}
)
WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    unified = unicodedata.normalize("NFC", text).translate(TYPOGRAPHIC_APOSTROPHES)
    return WHITESPACE.sub(" ", unified.strip()).lower()
