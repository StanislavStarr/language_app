MAX_WORD_CHARS = 100
MAX_SENTENCE_CHARS = 500
MAX_GLOSS_CHARS = 300


def prompt_text(value: str, limit: int) -> str:
    clipped = value.strip()[:limit]
    return clipped.replace("<", "&lt;").replace(">", "&gt;")
