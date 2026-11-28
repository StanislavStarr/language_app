import hashlib
from collections.abc import Sequence

from app.integrations.ai.prompts.select_sense import PROMPT_VERSION
from app.integrations.ai.provider import SelectSenseRequest, SenseCandidate
from app.integrations.nlp.normalization import normalize_text
from app.modules.lexicon.ai_access import AiAccess
from app.modules.lexicon.ai_calls import call_with_one_retry
from app.modules.lexicon.lookup_target import LookupTarget
from app.modules.lexicon.models import Lexeme, Meaning, SenseSelection
from app.modules.lexicon.repository import LexemeRepository
from app.modules.lexicon.schemas import RecommendedMeaning

SELECTION_CANDIDATES_LIMIT = 12


def context_hash(target: LookupTarget) -> str:
    payload = f"{normalize_text(target.sentence or '')}\n{target.text}"
    return hashlib.sha256(payload.encode()).hexdigest()


def recommendation(selection: SenseSelection, meaning_ids: set[int]) -> RecommendedMeaning | None:
    chosen = selection.selected_meaning_id
    if chosen is None or chosen not in meaning_ids:
        return None
    return RecommendedMeaning(
        meaning_id=chosen,
        contextual_translation=selection.contextual_translation,
        confidence=selection.confidence,
    )


class SenseChooser:
    def __init__(self, repository: LexemeRepository) -> None:
        self._repository = repository

    async def choose(
        self, ai: AiAccess, lexeme: Lexeme, meanings: Sequence[Meaning], target: LookupTarget
    ) -> RecommendedMeaning | None:
        if target.sentence is None:
            return None
        digest = context_hash(target)
        meaning_ids = {meaning.id for meaning in meanings}
        cached = await self._repository.find_sense_selection(lexeme.id, digest, PROMPT_VERSION)
        if cached is not None:
            return recommendation(cached, meaning_ids)
        provider = await ai.provider()
        if provider is None:
            return None
        candidates = tuple(
            SenseCandidate(meaning.id, meaning.part_of_speech.value, meaning.gloss)
            for meaning in meanings[:SELECTION_CANDIDATES_LIMIT]
        )
        request = SelectSenseRequest(target.text, target.sentence, candidates)
        result = await call_with_one_retry("select_sense", lambda: provider.select_sense(request))
        if result is None:
            return None
        selection = SenseSelection(
            lexeme_id=lexeme.id,
            context_hash=digest,
            selected_meaning_id=result.value.selected_meaning_id,
            contextual_translation=result.value.contextual_translation,
            confidence=result.value.confidence,
            model=result.model,
            prompt_version=result.prompt_version,
        )
        await self._repository.save_sense_selection(selection)
        return recommendation(selection, meaning_ids)
