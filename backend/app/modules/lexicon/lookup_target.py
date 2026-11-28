import re
from dataclasses import dataclass

import structlog

from app.integrations.nlp.normalization import normalize_text
from app.integrations.nlp.provider import NlpError, TextAnalyzer
from app.modules.lexicon.enums import LexemeType, PartOfSpeech
from app.modules.lexicon.part_of_speech import UNIVERSAL_TO_PART_OF_SPEECH

logger = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class LookupTarget:
    text: str
    sentence: str | None
    candidates: tuple[str, ...]
    part_of_speech: PartOfSpeech | None

    @property
    def lexeme_type(self) -> LexemeType:
        return LexemeType.PHRASE if " " in self.text else LexemeType.WORD


def locate(text: str, sentence: str | None) -> tuple[str, int]:
    if sentence is not None:
        found = re.search(rf"(?<!\w){re.escape(text)}(?!\w)", sentence, re.IGNORECASE)
        if found is not None:
            return sentence, found.start()
    return text, 0


async def build_target(analyzer: TextAnalyzer, text: str, sentence: str | None) -> LookupTarget:
    normalized = normalize_text(text)
    context = sentence.strip() if sentence and sentence.strip() else None
    analysed, start = locate(normalized, context)
    lemmas: list[str] = []
    part_of_speech: PartOfSpeech | None = None
    try:
        found = await analyzer.lemma_candidates(analysed, start, start + len(normalized))
    except (NlpError, OSError):
        logger.warning("nlp_unavailable")
        found = []
    for candidate in found:
        lemmas.append(candidate.lemma)
        part_of_speech = part_of_speech or UNIVERSAL_TO_PART_OF_SPEECH.get(candidate.pos.value)
    candidates = tuple(dict.fromkeys([*lemmas, normalized]))
    return LookupTarget(normalized, context, candidates, part_of_speech)
