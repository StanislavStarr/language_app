from collections.abc import Iterable

from pydantic import BaseModel

from app.integrations.ai.schemas.words import contains_any

MIN_TEXT_LENGTH = 10
MAX_TEXT_LENGTH = 200


class MeaningContentOutput(BaseModel):
    definition: str
    example: str


def check_meaning_content(output: MeaningContentOutput, target_forms: Iterable[str]) -> None:
    for name, text in (("definition", output.definition), ("example", output.example)):
        if not MIN_TEXT_LENGTH <= len(text.strip()) <= MAX_TEXT_LENGTH:
            message = f"the {name} must be {MIN_TEXT_LENGTH}-{MAX_TEXT_LENGTH} characters long"
            raise ValueError(message)
    forms = tuple(target_forms)
    if contains_any(output.definition, forms):
        message = "the definition contains the target word or one of its forms"
        raise ValueError(message)
    if not contains_any(output.example, forms):
        message = "the example does not contain the target word or one of its forms"
        raise ValueError(message)
