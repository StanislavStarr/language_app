from typing import Annotated

from fastapi import Depends, Request

from app.core.database import SessionDep
from app.modules.languages.dependencies import LanguageServiceDep
from app.modules.lexicon.repository import LexemeRepository
from app.modules.lexicon.service import LexiconProviders, LookupCollaborators, LookupService
from app.modules.usage.dependencies import UsageServiceDep
from app.modules.vocabulary.access import build_vocabulary_access


def get_lexicon_providers(request: Request) -> LexiconProviders:
    providers: LexiconProviders = request.app.state.lexicon_providers
    return providers


type LexiconProvidersDep = Annotated[LexiconProviders, Depends(get_lexicon_providers)]


def get_lookup_service(
    session: SessionDep,
    providers: LexiconProvidersDep,
    usage: UsageServiceDep,
    languages: LanguageServiceDep,
) -> LookupService:
    return LookupService(
        session,
        LexemeRepository(session),
        providers,
        LookupCollaborators(usage, languages, build_vocabulary_access(session)),
    )


type LookupServiceDep = Annotated[LookupService, Depends(get_lookup_service)]
