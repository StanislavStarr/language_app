import re

CYRILLIC = re.compile(r"[Ѐ-ӿ]")
LATIN = re.compile(r"[A-Za-z]")
FORBIDDEN_SYMBOLS = frozenset("()[]{}<>")


def is_short_russian_text(text: str, limit: int) -> bool:
    stripped = text.strip()
    return (
        bool(stripped)
        and len(stripped) <= limit
        and CYRILLIC.search(stripped) is not None
        and LATIN.search(stripped) is None
        and FORBIDDEN_SYMBOLS.isdisjoint(stripped)
    )
