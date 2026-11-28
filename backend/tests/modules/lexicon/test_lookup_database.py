from app.integrations.nlp.provider import UniversalPos
from app.integrations.nlp.spacy_analyzer import SpacyTextAnalyzer
from app.modules.lexicon.enums import LexemeType
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.factories import bearer, create_lexeme, create_meaning, sign_in_new_device
from tests.fakes.nlp import FakeTextAnalyzer
from tests.modules.lexicon.conftest import InstallProviders
from tests.modules.lexicon.lookup_helpers import LOOKUP_URL, lookup


async def test_known_word_is_answered_from_the_database_without_any_provider(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    bank = await create_lexeme(db_session, "bank", forms=["banks"])
    await create_meaning(db_session, bank, "An institution.", 1, translations={"ru": ["банк"]})
    await create_meaning(db_session, bank, "A river bank.", 2, translations={"ru": ["вал"]})

    response = await lookup(client, "  Bank ")

    body = response.json()
    assert response.status_code == 200
    assert body["lexeme"] == {
        "id": bank.id,
        "text": "bank",
        "lemma": "bank",
        "ipa": None,
        "audio_url": None,
    }
    assert [(m["gloss"], m["translations"]) for m in body["meanings"]] == [
        ("An institution.", ["банк"]),
        ("A river bank.", ["вал"]),
    ]
    assert body["has_more"] is False
    assert body["recommended"] is None
    assert body["user_meaning_ids"] == []
    assert body["typo_suggestion"] is None
    assert body["ai_limited"] is False


async def test_inflected_form_is_found_through_lexeme_form(
    client: AsyncClient, db_session: AsyncSession, install_providers: InstallProviders
) -> None:
    install_providers(analyzer=FakeTextAnalyzer({"went": ("go", UniversalPos.VERB)}))
    go = await create_lexeme(db_session, "go", forms=["went"])
    await create_meaning(db_session, go, "To move.", 1, translations={"ru": ["идти"]})

    body = (await lookup(client, "went", "He went home.")).json()

    assert body["lexeme"]["id"] == go.id
    assert body["lexeme"]["text"] == "went"
    assert body["lexeme"]["lemma"] == "go"


async def test_form_is_found_even_when_the_text_analyser_has_no_lemma(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    go = await create_lexeme(db_session, "go", forms=["went"])
    await create_meaning(db_session, go, "To move.", 1, translations={"ru": ["идти"]})

    body = (await lookup(client, "went")).json()

    assert body["lexeme"]["lemma"] == "go"


async def test_context_picks_the_lexeme_the_sentence_means(
    client: AsyncClient,
    db_session: AsyncSession,
    install_providers: InstallProviders,
    spacy_analyzer: SpacyTextAnalyzer,
) -> None:
    install_providers(analyzer=spacy_analyzer)
    see = await create_lexeme(db_session, "see", forms=["saw", "seen"])
    saw = await create_lexeme(db_session, "saw")
    for lexeme in (see, saw):
        await create_meaning(
            db_session, lexeme, f"Meaning of {lexeme.text}.", 1, translations={"ru": ["касса"]}
        )

    verb = (await lookup(client, "saw", "I saw him yesterday.")).json()
    noun = (await lookup(client, "saw", "She bought a rusty saw.")).json()

    assert verb["lexeme"]["lemma"] == "see"
    assert noun["lexeme"]["lemma"] == "saw"


async def test_phrase_is_found_by_the_lemma_of_its_first_word(
    client: AsyncClient,
    db_session: AsyncSession,
    install_providers: InstallProviders,
    spacy_analyzer: SpacyTextAnalyzer,
) -> None:
    install_providers(analyzer=spacy_analyzer)
    phrase = await create_lexeme(db_session, "look forward to", lexeme_type=LexemeType.PHRASE)
    await create_meaning(db_session, phrase, "To anticipate.", 1, translations={"ru": ["ждать"]})

    body = (await lookup(client, "looked forward to", "She looked forward to it.")).json()

    assert body["lexeme"]["id"] == phrase.id


async def test_first_page_has_three_meanings_and_the_rest_come_by_offset(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    run = await create_lexeme(db_session, "run")
    for order in range(1, 6):
        await create_meaning(
            db_session, run, f"Meaning {order}.", order, translations={"ru": ["идти"]}
        )
    token = await sign_in_new_device(client)
    headers = bearer(token)

    first = (
        await client.post(LOOKUP_URL, json={"source": "manual", "text": "run"}, headers=headers)
    ).json()
    rest = await client.get(f"/api/v1/lexemes/{run.id}/meanings?offset=3", headers=headers)
    page = await client.get(f"/api/v1/lexemes/{run.id}/meanings?offset=1&limit=2", headers=headers)
    beyond = await client.get(f"/api/v1/lexemes/{run.id}/meanings?offset=10", headers=headers)

    assert [m["gloss"] for m in first["meanings"]] == ["Meaning 1.", "Meaning 2.", "Meaning 3."]
    assert first["has_more"] is True
    assert [m["gloss"] for m in rest.json()["meanings"]] == ["Meaning 4.", "Meaning 5."]
    assert rest.json()["has_more"] is False
    assert [m["gloss"] for m in page.json()["meanings"]] == ["Meaning 2.", "Meaning 3."]
    assert page.json()["has_more"] is True
    assert beyond.json() == {"meanings": [], "has_more": False}


async def test_meanings_of_an_unknown_lexeme_are_not_found(client: AsyncClient) -> None:
    token = await sign_in_new_device(client)

    response = await client.get("/api/v1/lexemes/999999/meanings", headers=bearer(token))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "lexeme_not_found"


async def test_page_size_is_bounded(client: AsyncClient) -> None:
    token = await sign_in_new_device(client)

    response = await client.get("/api/v1/lexemes/1/meanings?limit=21", headers=bearer(token))

    assert response.status_code == 422
