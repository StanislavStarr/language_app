import re
from collections.abc import Iterable


def contains_any(text: str, words: Iterable[str]) -> bool:
    alternatives = [re.escape(word.lower()) for word in words if word.strip()]
    if not alternatives:
        return False
    pattern = r"(?<!\w)(?:" + "|".join(alternatives) + r")(?!\w)"
    return re.search(pattern, text.lower()) is not None
