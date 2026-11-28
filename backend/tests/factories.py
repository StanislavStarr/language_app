from collections.abc import Mapping, Sequence
from uuid import UUID, uuid4

from app.modules.languages.repository import LanguageRepository
from app.modules.languages.service import LanguageService
from app.modules.lexicon.enums import (
    LexemeType,
    LexiconSource,
    PartOfSpeech,
    TranslationSource,
)
from app.modules.lexicon.models import Lexeme, LexemeForm, Meaning, Translation
from app.modules.users.models import User
from app.modules.users.repository import UserRepository
from app.modules.users.service import UserService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

DEVICE_SECRET = "s" * 43


async def sign_in_new_device(
    client: AsyncClient, install_id: UUID | None = None, device_secret: str = DEVICE_SECRET
) -> str:
    response = await client.post(
        "/api/v1/auth/device",
        json={"install_id": str(install_id or uuid4()), "device_secret": device_secret},
    )
    assert response.status_code == 200
    access_token: str = response.json()["access_token"]
    return access_token


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_user(session: AsyncSession) -> User:
    languages = LanguageService(LanguageRepository(session))
    return await UserService(session, UserRepository(session), languages).add_new_user()


async def create_lexeme(
    session: AsyncSession,
    text: str,
    *,
    frequency_rank: int | None = None,
    forms: Sequence[str] = (),
    lexeme_type: LexemeType = LexemeType.WORD,
) -> Lexeme:
    language = await LanguageRepository(session).find_by_code("en")
    assert language is not None
    lexeme = Lexeme(
        language_id=language.id,
        text=text,
        normalized_text=text.lower(),
        type=lexeme_type,
        frequency_rank=frequency_rank,
        source=LexiconSource.WIKTIONARY,
    )
    session.add(lexeme)
    await session.flush()
    session.add_all(LexemeForm(lexeme_id=lexeme.id, form_normalized=form) for form in forms)
    await session.flush()
    return lexeme


async def create_meaning(
    session: AsyncSession,
    lexeme: Lexeme,
    gloss: str,
    sense_order: int,
    *,
    translations: Mapping[str, Sequence[str]] | None = None,
) -> Meaning:
    meaning = Meaning(
        lexeme_id=lexeme.id,
        part_of_speech=PartOfSpeech.NOUN,
        gloss=gloss,
        sense_order=sense_order,
        source=LexiconSource.WIKTIONARY,
    )
    session.add(meaning)
    await session.flush()
    for language_code, texts in (translations or {}).items():
        language = await LanguageRepository(session).find_by_code(language_code)
        assert language is not None
        session.add_all(
            Translation(
                meaning_id=meaning.id,
                language_id=language.id,
                text=text,
                source=TranslationSource.WIKTIONARY,
            )
            for text in texts
        )
    await session.flush()
    return meaning
