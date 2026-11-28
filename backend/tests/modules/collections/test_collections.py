from uuid import uuid4

from app.modules.collections.constants import MAX_COLLECTIONS_PER_USER
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.modules.vocabulary.vocabulary_api import (
    COLLECTIONS_URL,
    VOCABULARY_URL,
    create_collection,
    new_headers,
    new_meaning_id,
    save,
)


async def test_a_collection_can_be_created_read_listed_renamed_and_deleted(
    client: AsyncClient,
) -> None:
    headers = await new_headers(client)

    created = await client.post(
        COLLECTIONS_URL, json={"name": "  Travel ", "description": "Trips"}, headers=headers
    )
    collection_id = created.json()["id"]
    url = f"{COLLECTIONS_URL}/{collection_id}"
    renamed = await client.patch(url, json={"name": "Journeys"}, headers=headers)
    cleared = await client.patch(url, json={"description": None}, headers=headers)
    listed = await client.get(COLLECTIONS_URL, headers=headers)
    deleted = await client.delete(url, headers=headers)

    assert created.status_code == 201
    assert created.json() == {
        "id": collection_id,
        "name": "Travel",
        "description": "Trips",
        "item_count": 0,
    }
    assert (renamed.json()["name"], renamed.json()["description"]) == ("Journeys", "Trips")
    assert cleared.json()["description"] is None
    assert [c["name"] for c in listed.json()] == ["Journeys"]
    assert deleted.status_code == 204
    assert (await client.get(url, headers=headers)).status_code == 404


async def test_names_are_unique_per_user_ignoring_case(client: AsyncClient) -> None:
    headers = await new_headers(client)
    other = await new_headers(client)
    first = await create_collection(client, headers, "Travel")
    second = await create_collection(client, headers, "Work")

    duplicate = await client.post(COLLECTIONS_URL, json={"name": "TRAVEL"}, headers=headers)
    rename_clash = await client.patch(
        f"{COLLECTIONS_URL}/{second}", json={"name": "travel"}, headers=headers
    )
    same_name_other_user = await client.post(
        COLLECTIONS_URL, json={"name": "Travel"}, headers=other
    )
    keep_own_name = await client.patch(
        f"{COLLECTIONS_URL}/{first}", json={"name": "Travel"}, headers=headers
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "collection_name_taken"
    assert rename_clash.status_code == 409
    assert same_name_other_user.status_code == 201
    assert keep_own_name.status_code == 200


async def test_the_number_of_collections_is_limited(client: AsyncClient) -> None:
    headers = await new_headers(client)
    for number in range(MAX_COLLECTIONS_PER_USER):
        await create_collection(client, headers, f"Topic {number}")

    response = await client.post(COLLECTIONS_URL, json={"name": "One more"}, headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "collection_limit_reached"
    assert (
        len((await client.get(COLLECTIONS_URL, headers=headers)).json()) == MAX_COLLECTIONS_PER_USER
    )


async def test_invalid_names_are_rejected(client: AsyncClient) -> None:
    headers = await new_headers(client)

    for body in ({"name": ""}, {"name": "   "}, {"name": "n" * 61}, {}, {"name": "ok", "x": 1}):
        response = await client.post(COLLECTIONS_URL, json=body, headers=headers)
        assert response.status_code == 422


async def test_items_are_added_counted_and_removed_without_deleting_the_word(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await new_headers(client)
    collection_id = await create_collection(client, headers)
    item = (await save(client, headers, await new_meaning_id(db_session, "bank"))).json()
    items_url = f"{COLLECTIONS_URL}/{collection_id}/items"

    added = await client.post(items_url, json={"vocabulary_item_id": item["id"]}, headers=headers)
    added_again = await client.post(
        items_url, json={"vocabulary_item_id": item["id"]}, headers=headers
    )
    counted = await client.get(f"{COLLECTIONS_URL}/{collection_id}", headers=headers)
    card = await client.get(f"{VOCABULARY_URL}/{item['id']}", headers=headers)
    removed = await client.delete(f"{items_url}/{item['id']}", headers=headers)
    removed_again = await client.delete(f"{items_url}/{item['id']}", headers=headers)

    assert (added.status_code, added_again.status_code) == (204, 204)
    assert counted.json()["item_count"] == 1
    assert [c["id"] for c in card.json()["collections"]] == [str(collection_id)]
    assert (removed.status_code, removed_again.status_code) == (204, 204)
    assert (await client.get(f"{COLLECTIONS_URL}/{collection_id}", headers=headers)).json()[
        "item_count"
    ] == 0
    assert (await client.get(f"{VOCABULARY_URL}/{item['id']}", headers=headers)).status_code == 200


async def test_deleting_a_collection_keeps_its_words(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await new_headers(client)
    collection_id = await create_collection(client, headers)
    meaning_id = await new_meaning_id(db_session, "bank")
    item = (await save(client, headers, meaning_id, [collection_id])).json()

    await client.delete(f"{COLLECTIONS_URL}/{collection_id}", headers=headers)

    card = (await client.get(f"{VOCABULARY_URL}/{item['id']}", headers=headers)).json()
    assert card["collections"] == []


async def test_someone_elses_collections_and_items_are_not_found(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = await new_headers(client)
    stranger = await new_headers(client)
    collection_id = await create_collection(client, owner)
    owners_item = (await save(client, owner, await new_meaning_id(db_session, "bank"))).json()
    strangers_collection = await create_collection(client, stranger)
    url = f"{COLLECTIONS_URL}/{collection_id}"

    foreign_collection = [
        await client.get(url, headers=stranger),
        await client.patch(url, json={"name": "Mine"}, headers=stranger),
        await client.delete(url, headers=stranger),
        await client.post(
            f"{url}/items", json={"vocabulary_item_id": owners_item["id"]}, headers=stranger
        ),
        await client.delete(f"{url}/items/{owners_item['id']}", headers=stranger),
    ]
    foreign_item = await client.post(
        f"{COLLECTIONS_URL}/{strangers_collection}/items",
        json={"vocabulary_item_id": owners_item["id"]},
        headers=stranger,
    )
    missing = await client.get(f"{COLLECTIONS_URL}/{uuid4()}", headers=owner)

    assert [r.status_code for r in foreign_collection] == [404] * 5
    assert {r.json()["error"]["code"] for r in foreign_collection} == {"collection_not_found"}
    assert foreign_item.status_code == 404
    assert foreign_item.json()["error"]["code"] == "vocabulary_item_not_found"
    assert missing.status_code == 404
    assert (await client.get(url, headers=owner)).json()["item_count"] == 0


async def test_collections_require_authentication(client: AsyncClient) -> None:
    assert (await client.get(COLLECTIONS_URL)).status_code == 401
    assert (await client.post(COLLECTIONS_URL, json={"name": "x"})).status_code == 401
