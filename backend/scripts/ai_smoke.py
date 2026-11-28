import asyncio
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.core.config import get_settings
from app.integrations.ai.openai_provider import OpenAIProvider
from app.integrations.ai.provider import (
    AIError,
    AIProvider,
    AIResult,
    GenerateFallbackMeaningsRequest,
    GenerateMeaningContentRequest,
    SelectSenseRequest,
    SenseCandidate,
    TranslateMeaningsRequest,
)
from app.integrations.ai.schemas.sense_selection import SenseSelectionOutput

MONEY = SenseCandidate(1, "noun", "An institution where one can place and borrow money.")
RIVER = SenseCandidate(2, "noun", "The land alongside or sloping down to a river or lake.")
TILT = SenseCandidate(3, "verb", "To tilt or incline laterally while turning.")
CANDIDATES = (MONEY, RIVER, TILT)


@dataclass(slots=True)
class Report:
    lines: list[str]
    failures: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def record(self, title: str, result: AIResult[object], passed: bool, detail: str) -> None:
        self.input_tokens += result.usage.input_tokens
        self.output_tokens += result.usage.output_tokens
        self.failures += int(not passed)
        self.lines.append(f"[{'OK' if passed else 'FAIL'}] {title}: {detail}")

    def error(self, title: str, error: AIError) -> None:
        self.failures += 1
        self.lines.append(f"[FAIL] {title}: {type(error).__name__}")


async def check[Output](
    report: Report,
    title: str,
    call: Awaitable[AIResult[Output]],
    judge: Callable[[Output], tuple[bool, str]],
) -> None:
    try:
        result = await call
    except AIError as error:
        report.error(title, error)
        return
    passed, detail = judge(result.value)
    report.record(title, result, passed, detail)


def expects_meaning(expected: int) -> Callable[[SenseSelectionOutput], tuple[bool, str]]:
    def judge(output: SenseSelectionOutput) -> tuple[bool, str]:
        return (
            output.selected_meaning_id == expected,
            f"id={output.selected_meaning_id} translation={output.contextual_translation} "
            f"confidence={output.confidence}",
        )

    return judge


async def run(provider: AIProvider) -> Report:
    report = Report([])
    for title, sentence, expected in (
        ("select_sense / money", "She deposited the check at the bank on Monday.", MONEY.id),
        ("select_sense / river", "They had a picnic on the bank of the river.", RIVER.id),
    ):
        await check(
            report,
            title,
            provider.select_sense(SelectSenseRequest("bank", sentence, CANDIDATES)),
            expects_meaning(expected),
        )
    for candidate in (MONEY, RIVER):
        await check(
            report,
            f"meaning_content / {candidate.id}",
            provider.generate_meaning_content(
                GenerateMeaningContentRequest(
                    "bank", ("banks",), candidate.part_of_speech, candidate.gloss, "B1"
                )
            ),
            lambda output: (True, f"definition={output.definition!r} example={output.example!r}"),
        )
    await check(
        report,
        "translate_meanings",
        provider.translate_meanings(TranslateMeaningsRequest("bank", CANDIDATES)),
        lambda output: (
            len(output.items) == len(CANDIDATES),
            "; ".join(
                f"{item.meaning_id}: {', '.join(item.translations)}" for item in output.items
            ),
        ),
    )
    await check(
        report,
        "fallback_meanings / real word",
        provider.generate_fallback_meanings(GenerateFallbackMeaningsRequest("petrichor", None)),
        lambda output: (output.found, f"found={output.found} meanings={len(output.meanings)}"),
    )
    await check(
        report,
        "fallback_meanings / gibberish",
        provider.generate_fallback_meanings(GenerateFallbackMeaningsRequest("qzxwvbnm", None)),
        lambda output: (not output.found, f"found={output.found}"),
    )
    return report


def main() -> None:
    try:
        provider = OpenAIProvider.from_settings(get_settings())
    except AIError as error:
        sys.stderr.write(f"{error}\n")
        raise SystemExit(2) from error
    report = asyncio.run(run(provider))
    for line in report.lines:
        sys.stdout.write(f"{line}\n")
    sys.stdout.write(
        f"tokens: input={report.input_tokens} output={report.output_tokens}; "
        f"failures={report.failures}\n"
    )
    raise SystemExit(1 if report.failures else 0)


if __name__ == "__main__":
    main()
