import base64

from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from tests.modules.vocabulary.vocabulary_api import (
    VOCABULARY_URL,
    create_collection,
    new_headers,
    new_meaning_id,
    save,
)


async def save_words(
    client: AsyncClient, session: AsyncSession, headers: dict[str, str], words: list[str]
) -> list[str]:
    ids = []
    for word in words:
        response = await save(client, headers, await new_meaning_id(session, word))
        ids.append(response.json()["id"])
    return ids


async def test_pages_follow_the_cursor_without_gaps_or_repeats(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await new_headers(client)
    saved = await save_words(client, db_session, headers, ["a1", "b2", "c3", "d4", "e5"])
    seen: list[str] = []
    cursor: str | None = None

    for expected_size in (2, 2, 1):
        params = {"limit": "2", **({"cursor": cursor} if cursor else {})}
        page = (await client.get(VOCABULARY_URL, params=params, headers=headers)).json()
        assert len(page["items"]) == expected_size
        seen += [item["id"] for item in page["items"]]
        cursor = page["next_cursor"]

    assert cursor is None
    assert sorted(seen) == sorted(saved)
    assert len(set(seen)) == 5


async def test_last_full_page_has_no_next_cursor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await new_headers(client)
    await save_words(client, db_session, headers, ["a1", "b2"])

    page = (await client.get(VOCABULARY_URL, params={"limit": "2"}, headers=headers)).json()

    assert len(page["items"]) == 2
    assert page["next_cursor"] is None


async def test_the_list_holds_only_the_callers_items(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    mine = await new_headers(client)
    theirs = await new_headers(client)
    await save_words(client, db_session, mine, ["a1"])
    await save_words(client, db_session, theirs, ["b2", "c3"])

    page = (await client.get(VOCABULARY_URL, headers=mine)).json()

    assert [item["lexeme"]["text"] for item in page["items"]] == ["a1"]


async def test_filter_by_collection_returns_only_its_items(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await new_headers(client)
    travel = await create_collection(client, headers)
    inside = (await save(client, headers, await new_meaning_id(db_session, "a1"), [travel])).json()
    await save_words(client, db_session, headers, ["b2"])

    page = (
        await client.get(VOCABULARY_URL, params={"collection_id": str(travel)}, headers=headers)
    ).json()

    assert [item["id"] for item in page["items"]] == [inside["id"]]


async def test_someone_elses_collection_filter_is_not_found(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = await new_headers(client)
    stranger = await new_headers(client)
    travel = await create_collection(client, owner)
    await save(client, owner, await new_meaning_id(db_session, "a1"), [travel])

    response = await client.get(
        VOCABULARY_URL, params={"collection_id": str(travel)}, headers=stranger
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "collection_not_found"


async def test_filter_by_book_returns_nothing_until_books_exist(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await new_headers(client)
    await save_words(client, db_session, headers, ["a1"])

    page = await client.get(
        VOCABULARY_URL, params={"book_id": "00000000-0000-0000-0000-000000000001"}, headers=headers
    )

    assert page.json()["items"] == []


async def test_invalid_cursor_and_limit_are_rejected(client: AsyncClient) -> None:
    headers = await new_headers(client)

    bad_cursor = await client.get(
        VOCABULARY_URL, params={"cursor": "not-a-cursor"}, headers=headers
    )
    zero = await client.get(VOCABULARY_URL, params={"limit": "0"}, headers=headers)
    huge = await client.get(VOCABULARY_URL, params={"limit": "101"}, headers=headers)

    assert bad_cursor.status_code == 422
    assert bad_cursor.json()["error"]["code"] == "invalid_cursor"
    assert (zero.status_code, huge.status_code) == (422, 422)


async def test_listing_cards_does_not_query_per_item(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await new_headers(client)
    await save_words(client, db_session, headers, ["a1", "b2", "c3", "d4", "e5", "f6"])
    statements: list[str] = []
    engine = db_session.bind.sync_engine  # type: ignore[union-attr]

    def record(_conn: object, _cursor: object, statement: str, *_args: object) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        await client.get(VOCABULARY_URL, headers=headers)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert 1 <= len(statements) <= 8


async def test_cursor_without_a_timezone_is_rejected(client: AsyncClient) -> None:
    headers = await new_headers(client)
    naive = base64.urlsafe_b64encode(
        b"2026-01-01T00:00:00|00000000-0000-0000-0000-000000000001"
    ).decode()

    response = await client.get(VOCABULARY_URL, params={"cursor": naive}, headers=headers)

    assert response.json()["error"]["code"] == "invalid_cursor"
