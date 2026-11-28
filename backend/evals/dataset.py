from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"


class SenseCandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    part_of_speech: str
    gloss: str


class SenseCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    word: str
    sentence: str
    candidates: list[SenseCandidateRecord]
    expected_id: int | None


class ContentCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    word: str
    forms: list[str]
    part_of_speech: str
    gloss: str
    levels: list[str]


def read_jsonl[Case: BaseModel](
    name: str, model: type[Case], limit: int | None = None
) -> list[Case]:
    lines = (DATASETS_DIR / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    cases = [model.model_validate_json(line) for line in lines if line.strip()]
    return take(cases, limit)


def take[Item](items: Sequence[Item], limit: int | None) -> list[Item]:
    return list(items if limit is None else items[:limit])
