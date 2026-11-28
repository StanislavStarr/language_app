from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.modules.languages.enums import CefrLevel
from app.modules.lexicon.enums import MeaningContentStatus
from app.modules.lexicon.models import MeaningContent
from app.modules.vocabulary.models import UserVocabularyItem
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.fakes.scheduler import RecordingScheduler
from tests.modules.vocabulary.vocabulary_api import (
    VOCABULARY_URL,
    create_collection,
    new_headers,
    new_meaning_id,
    save,
)


async def test_saving_a_meaning_returns_the_whole_card(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await new_headers(client)
    meaning_id = await new_meaning_id(db_session, "bank", "A financial institution.")
    collection_id = await create_collection(client, headers)

    response = await save(
        client,
        headers,
        meaning_id,
        [collection_id],
        context_sentence="She went to the bank.",
        context_translation="банк",
    )

    body = response.json()
    assert response.status_code == 201
    assert body["lexeme"]["text"] == "bank"
    assert body["meaning"] == {
        "id": meaning_id,
        "part_of_speech": "noun",
        "gloss": "A financial institution.",
        "translations": ["штука"],
    }
    assert body["content"] is None
    assert body["source_type"] == "manual"
    assert body["source_context"] == "She went to the bank."
    assert body["context_translation"] == "банк"
    assert body["enrichment_status"] == "pending"
    assert body["study_count"] == 0
    assert body["collections"] == [{"id": str(collection_id), "name": "Travel"}]


async def test_saving_the_same_meaning_twice_is_a_conflict_with_the_existing_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await new_headers(client)
    meaning_id = await new_meaning_id(db_session, "bank")
    first = (await save(client, headers, meaning_id)).json()

    second = await save(client, headers, meaning_id)

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "already_in_vocabulary"
    assert second.json()["error"]["details"] == {"vocabulary_item_id": first["id"]}


async def test_two_users_can_save_the_same_meaning(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    meaning_id = await new_meaning_id(db_session, "bank")

    first = await save(client, await new_headers(client), meaning_id)
    second = await save(client, await new_headers(client), meaning_id)

    assert (first.status_code, second.status_code) == (201, 201)


async def test_unknown_meaning_is_not_found(client: AsyncClient) -> None:
    response = await save(client, await new_headers(client), 999_999)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "meaning_not_found"


async def test_someone_elses_collection_is_not_found_and_nothing_is_saved(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = await new_headers(client)
    stranger = await new_headers(client)
    foreign_collection = await create_collection(client, owner)
    meaning_id = await new_meaning_id(db_session, "bank")

    response = await save(client, stranger, meaning_id, [foreign_collection])

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "collection_not_found"
    assert (await client.get(VOCABULARY_URL, headers=stranger)).json()["items"] == []
    assert (await save(client, stranger, meaning_id)).status_code == 201


async def test_the_card_carries_prepared_content(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await new_headers(client)
    meaning_id = await new_meaning_id(db_session, "bank")
    item = (await save(client, headers, meaning_id)).json()
    content = MeaningContent(
        meaning_id=meaning_id,
        cefr_level=CefrLevel.B1,
        definition="A place for money.",
        example="I visited the bank.",
        status=MeaningContentStatus.READY,
        provider="fake",
        model="fake",
        prompt_version="v1",
        generated_at=datetime.now(UTC),
    )
    db_session.add(content)
    await db_session.flush()
    stored = await db_session.get_one(UserVocabularyItem, item["id"])
    stored.meaning_content_id = content.id
    await db_session.flush()

    body = (await client.get(f"{VOCABULARY_URL}/{item['id']}", headers=headers)).json()

    assert body["content"] == {"definition": "A place for money.", "example": "I visited the bank."}


async def test_personal_note_and_context_translation_can_be_changed_and_cleared(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await new_headers(client)
    item = (await save(client, headers, await new_meaning_id(db_session, "bank"))).json()
    url = f"{VOCABULARY_URL}/{item['id']}"

    changed = await client.patch(
        url, json={"personal_note": "money", "context_translation": "банк"}, headers=headers
    )
    only_note_cleared = await client.patch(url, json={"personal_note": None}, headers=headers)

    assert changed.json()["personal_note"] == "money"
    assert only_note_cleared.json()["personal_note"] is None
    assert only_note_cleared.json()["context_translation"] == "банк"


async def test_deleting_an_item_removes_it_from_the_vocabulary_and_its_collections(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await new_headers(client)
    collection_id = await create_collection(client, headers)
    meaning_id = await new_meaning_id(db_session, "bank")
    item = (await save(client, headers, meaning_id, [collection_id])).json()
    url = f"{VOCABULARY_URL}/{item['id']}"

    deleted = await client.delete(url, headers=headers)

    assert deleted.status_code == 204
    assert (await client.get(url, headers=headers)).status_code == 404
    collection = await client.get(f"/api/v1/collections/{collection_id}", headers=headers)
    assert collection.json()["item_count"] == 0
    assert (await save(client, headers, meaning_id)).status_code == 201


async def test_someone_elses_item_is_not_found_for_every_action(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = await new_headers(client)
    stranger = await new_headers(client)
    item = (await save(client, owner, await new_meaning_id(db_session, "bank"))).json()
    url = f"{VOCABULARY_URL}/{item['id']}"

    responses = [
        await client.get(url, headers=stranger),
        await client.patch(url, json={"personal_note": "x"}, headers=stranger),
        await client.delete(url, headers=stranger),
        await client.get(f"{VOCABULARY_URL}/{uuid4()}", headers=owner),
    ]

    assert [r.status_code for r in responses] == [404, 404, 404, 404]
    assert {r.json()["error"]["code"] for r in responses} == {"vocabulary_item_not_found"}
    assert (await client.get(url, headers=owner)).status_code == 200


async def test_input_is_validated(client: AsyncClient, db_session: AsyncSession) -> None:
    headers = await new_headers(client)
    meaning_id = await new_meaning_id(db_session, "bank")

    too_long_context = await save(client, headers, meaning_id, context_sentence="c" * 501)
    too_long_note = await client.patch(
        f"{VOCABULARY_URL}/{uuid4()}", json={"personal_note": "n" * 501}, headers=headers
    )
    book_source = await client.post(
        VOCABULARY_URL, json={"source": "book", "meaning_id": meaning_id}, headers=headers
    )

    assert too_long_context.status_code == 422
    assert too_long_note.status_code == 422
    assert book_source.status_code == 422


async def test_every_endpoint_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(VOCABULARY_URL)).status_code == 401
    assert (await client.post(VOCABULARY_URL, json={})).status_code == 401
    assert (await client.get(f"{VOCABULARY_URL}/forms")).status_code == 401


async def test_saving_schedules_enrichment_once_for_the_new_item(
    client: AsyncClient, db_session: AsyncSession, scheduler: RecordingScheduler
) -> None:
    headers = await new_headers(client)
    meaning_id = await new_meaning_id(db_session, "bank")

    created = await save(client, headers, meaning_id)
    await save(client, headers, meaning_id)

    assert scheduler.scheduled == [UUID(created.json()["id"])]


async def test_failed_saves_do_not_schedule_enrichment(
    client: AsyncClient, scheduler: RecordingScheduler
) -> None:
    headers = await new_headers(client)

    await save(client, headers, 999_999)

    assert scheduler.scheduled == []
