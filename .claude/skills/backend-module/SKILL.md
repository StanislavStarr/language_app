---
name: backend-module
description: Create or extend a FastAPI domain module in backend/app/modules (router, schemas, models, repository, service, exceptions, dependencies, jobs) following the service-layer architecture. Use for any new endpoint, use case or backend module.
---

# Backend module (service layer)

Rules: `backend/CLAUDE.md`. Architecture: `docs/ARCHITECTURE.md` §4, §7.

## Checklist

1. Which module owns this behaviour? Reuse an existing module if the concept belongs there.
2. Which use case(s)? One public service method per use case.
3. Contract first: request/response schemas and error codes (`docs/ARCHITECTURE.md` §7).
4. Data: does a table change? → skill `backend-migration`.
5. Integrations needed? → depend on the Protocol, not the implementation.
6. Background work? → `jobs.py` task calling a service method, deferred after commit.
7. Tests → skill `backend-testing`.
8. Register the router in `app/api.py`; models are imported for Alembic autogenerate.

## Templates

Adapt names; do not copy unused parts. No comments in real code.

### exceptions.py

```python
from app.core.errors import AppError


class CollectionNotFound(AppError):
    def __init__(self) -> None:
        super().__init__(code="collection_not_found", message="Collection not found", status_code=404)


class CollectionNameTaken(AppError):
    def __init__(self, name: str) -> None:
        super().__init__(
            code="collection_name_taken",
            message="Collection with this name already exists",
            status_code=409,
            details={"name": name},
        )
```

### schemas.py

```python
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.collections.constants import COLLECTION_NAME_MAX_LENGTH


class CollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=COLLECTION_NAME_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=300)


class CollectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    item_count: int
```

### repository.py

```python
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.collections.models import Collection


class CollectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_user(self, collection_id: UUID, user_id: UUID) -> Collection | None:
        statement = select(Collection).where(
            Collection.id == collection_id,
            Collection.user_id == user_id,
        )
        return await self._session.scalar(statement)

    async def exists_with_name(self, user_id: UUID, name: str) -> bool:
        statement = select(func.count()).where(
            Collection.user_id == user_id,
            func.lower(Collection.name) == name.lower(),
        )
        return bool(await self._session.scalar(statement))

    def add(self, collection: Collection) -> None:
        self._session.add(collection)
```

### service.py

```python
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.collections.exceptions import CollectionNameTaken
from app.modules.collections.models import Collection
from app.modules.collections.repository import CollectionRepository
from app.modules.collections.schemas import CollectionCreate


class CollectionService:
    def __init__(self, session: AsyncSession, repository: CollectionRepository) -> None:
        self._session = session
        self._repository = repository

    async def create_collection(self, user_id: UUID, payload: CollectionCreate) -> Collection:
        if await self._repository.exists_with_name(user_id, payload.name):
            raise CollectionNameTaken(payload.name)
        collection = Collection(user_id=user_id, name=payload.name, description=payload.description)
        self._repository.add(collection)
        await self._session.commit()
        await self._session.refresh(collection)
        return collection
```

If the use case must start a job: commit first, then `await some_job.defer_async(item_id=str(item.id))`.

### dependencies.py

```python
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.modules.collections.repository import CollectionRepository
from app.modules.collections.service import CollectionService


def get_collection_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CollectionService:
    return CollectionService(session=session, repository=CollectionRepository(session))


CollectionServiceDep = Annotated[CollectionService, Depends(get_collection_service)]
```

Integrations are wired the same way (`get_ai_provider()` in `app/integrations/ai/dependencies.py`),
so tests can override them with fakes via `app.dependency_overrides`.

### router.py

```python
from fastapi import APIRouter, status

from app.modules.auth.dependencies import CurrentUser
from app.modules.collections.dependencies import CollectionServiceDep
from app.modules.collections.schemas import CollectionCreate, CollectionResponse

router = APIRouter(prefix="/collections", tags=["collections"])


@router.post(
    "",
    response_model=CollectionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "collection_name_taken"}},
)
async def create_collection(
    payload: CollectionCreate,
    user: CurrentUser,
    service: CollectionServiceDep,
) -> CollectionResponse:
    collection = await service.create_collection(user.id, payload)
    return CollectionResponse.model_validate(collection)
```

### jobs.py

```python
from app.core.jobs import jobs_app
from app.core.database import session_scope
from app.modules.enrichment.service import build_enrichment_service


@jobs_app.task(name="enrich_vocabulary_item", queue="enrichment", retry=3)
async def enrich_vocabulary_item(item_id: str) -> None:
    async with session_scope() as session:
        service = build_enrichment_service(session)
        await service.enrich_item(item_id)
```

## Anti-patterns to reject

- SQL or `session.execute` in a router or service (services call repositories).
- `HTTPException` raised from a service.
- A repository method that commits or decides business rules.
- One `schemas.py` model reused for create, update and response "to save lines".
- Importing `app.modules.other.repository` from this module.
- Catch-all `except Exception` that hides errors (allowed only at job/provider boundary with logging and re-raise or status change).
