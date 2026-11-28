import pytest
from app.integrations.ai.prompts.meaning_content import PROMPT_VERSION
from app.integrations.ai.provider import AIUnavailableError, GenerateMeaningContentRequest
from app.modules.enrichment.service import build_enrichment_service
from app.modules.languages.enums import CefrLevel
from app.modules.lexicon.enums import MeaningContentStatus
from app.modules.lexicon.models import MeaningContent
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import bearer, sign_in_new_device
from tests.fakes.fake_ai_provider import FakeAIProvider
from tests.modules.enrichment.enrichment_setup import (
    CONTENT,
    card,
    fake_ai,
    invalid_content,
    meaning_without_translation,
    saved_item,
)
from tests.modules.vocabulary.vocabulary_api import new_meaning_id


def names(ai: FakeAIProvider) -> list[str]:
    return [name for name, _ in ai.calls]


async def test_card_becomes_ready_with_translation_and_content(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, item_id = await saved_item(client, await meaning_without_translation(db_session))
    ai = fake_ai()

    await build_enrichment_service(db_session, ai).enrich_item(item_id, final_attempt=False)

    body = await card(client, headers, item_id)
    assert body["enrichment_status"] == "ready"
    assert body["content"] == {"definition": CONTENT.definition, "example": CONTENT.example}
    assert body["meaning"]["translations"] == ["ссуда"]  # type: ignore[index]
    assert names(ai) == ["translate_meanings", "generate_meaning_content"]


async def test_existing_translation_is_not_requested_again(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, item_id = await saved_item(client, await new_meaning_id(db_session, "bank"))
    ai = fake_ai()

    await build_enrichment_service(db_session, ai).enrich_item(item_id, final_attempt=False)

    assert names(ai) == ["generate_meaning_content"]
    assert (await card(client, headers, item_id))["enrichment_status"] == "ready"


async def test_content_uses_the_learners_level_and_the_word_forms(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await sign_in_new_device(client)
    headers = bearer(token)
    await client.patch("/api/v1/users/me", json={"cefr_level": "B2"}, headers=headers)
    _, item_id = await saved_item(client, await meaning_without_translation(db_session), headers)
    ai = fake_ai()

    await build_enrichment_service(db_session, ai).enrich_item(item_id, final_attempt=False)

    request = next(r for name, r in ai.calls if name == "generate_meaning_content")
    assert isinstance(request, GenerateMeaningContentRequest)
    assert request.cefr_level == "B2"
    assert set(request.forms) == {"bank", "banks"}
    stored = (await db_session.scalars(select(MeaningContent))).one()
    assert stored.cefr_level == CefrLevel.B2


async def test_failed_definition_leaves_a_partial_card_and_a_rerun_completes_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, item_id = await saved_item(client, await meaning_without_translation(db_session))
    broken = fake_ai(content=invalid_content)

    await build_enrichment_service(db_session, broken).enrich_item(item_id, final_attempt=False)

    partial = await card(client, headers, item_id)
    assert partial["enrichment_status"] == "partial"
    assert partial["content"] is None
    assert partial["meaning"]["translations"] == ["ссуда"]  # type: ignore[index]
    assert await db_session.scalar(select(func.count()).select_from(MeaningContent)) == 0

    healthy = fake_ai()
    await build_enrichment_service(db_session, healthy).enrich_item(item_id, final_attempt=False)

    assert (await card(client, headers, item_id))["enrichment_status"] == "ready"
    assert names(healthy) == ["generate_meaning_content"]


async def test_running_a_finished_item_again_does_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _, item_id = await saved_item(client, await meaning_without_translation(db_session))
    ai = fake_ai()
    service = build_enrichment_service(db_session, ai)

    await service.enrich_item(item_id, final_attempt=False)
    await service.enrich_item(item_id, final_attempt=False)

    assert len(ai.calls) == 2
    assert await db_session.scalar(select(func.count()).select_from(MeaningContent)) == 1


async def test_two_learners_of_one_meaning_cause_one_generation(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    meaning_id = await meaning_without_translation(db_session)
    first_headers, first_item = await saved_item(client, meaning_id)
    second_headers, second_item = await saved_item(client, meaning_id)
    ai = fake_ai()
    service = build_enrichment_service(db_session, ai)

    await service.enrich_item(first_item, final_attempt=False)
    await service.enrich_item(second_item, final_attempt=False)

    assert names(ai).count("generate_meaning_content") == 1
    assert names(ai).count("translate_meanings") == 1
    first = await card(client, first_headers, first_item)
    second = await card(client, second_headers, second_item)
    assert (first["enrichment_status"], second["enrichment_status"]) == ("ready", "ready")
    assert first["content"] == second["content"]


async def test_without_ai_the_card_fails_when_nothing_is_prepared(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, item_id = await saved_item(client, await meaning_without_translation(db_session))

    await build_enrichment_service(db_session, None).enrich_item(item_id, final_attempt=False)

    assert (await card(client, headers, item_id))["enrichment_status"] == "failed"


async def test_without_ai_prepared_parts_still_count(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, item_id = await saved_item(client, await new_meaning_id(db_session, "bank"))

    await build_enrichment_service(db_session, None).enrich_item(item_id, final_attempt=False)

    assert (await card(client, headers, item_id))["enrichment_status"] == "partial"


async def test_transient_outage_asks_for_a_retry_until_the_last_attempt(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, item_id = await saved_item(client, await meaning_without_translation(db_session))
    down = FakeAIProvider(error=AIUnavailableError("down"))
    service = build_enrichment_service(db_session, down)

    with pytest.raises(AIUnavailableError):
        await service.enrich_item(item_id, final_attempt=False)
    pending = await card(client, headers, item_id)
    await service.enrich_item(item_id, final_attempt=True)

    assert pending["enrichment_status"] == "enriching"
    assert (await card(client, headers, item_id))["enrichment_status"] == "failed"


async def test_item_removed_before_the_job_runs_is_ignored(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers, item_id = await saved_item(client, await meaning_without_translation(db_session))
    await client.delete(f"/api/v1/vocabulary/{item_id}", headers=headers)
    ai = fake_ai()

    await build_enrichment_service(db_session, ai).enrich_item(item_id, final_attempt=False)

    assert ai.calls == []


async def test_an_unfinished_content_row_is_completed_instead_of_duplicated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    meaning_id = await new_meaning_id(db_session, "bank")
    headers, item_id = await saved_item(client, meaning_id)
    db_session.add(
        MeaningContent(
            meaning_id=meaning_id,
            cefr_level=CefrLevel.A1,
            status=MeaningContentStatus.PENDING,
            provider="fake",
            model="fake",
            prompt_version=PROMPT_VERSION,
        )
    )
    await db_session.flush()

    await build_enrichment_service(db_session, fake_ai()).enrich_item(item_id, final_attempt=False)

    stored = (await db_session.scalars(select(MeaningContent))).one()
    assert stored.status == MeaningContentStatus.READY
    assert (await card(client, headers, item_id))["enrichment_status"] == "ready"
