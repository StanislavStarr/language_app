from collections.abc import Sequence
from dataclasses import dataclass

from app.integrations.ai.prompts.select_sense import PROMPT_VERSION
from app.integrations.ai.provider import (
    AIError,
    AIProvider,
    AIUsage,
    SelectSenseRequest,
    SenseCandidate,
)

from evals.concurrency import run_limited
from evals.dataset import SenseCase
from evals.report import (
    UNKNOWN_MODEL,
    Failure,
    Metric,
    SuiteReport,
    first_model,
    sum_usage,
)

ACCURACY_TARGET = 0.85


@dataclass(frozen=True, slots=True)
class Outcome:
    case: SenseCase
    selected: int | None
    error: str | None
    usage: AIUsage
    model: str

    @property
    def correct(self) -> bool:
        return self.error is None and self.selected == self.case.expected_id


async def judge_case(provider: AIProvider, case: SenseCase) -> Outcome:
    request = SelectSenseRequest(
        case.word,
        case.sentence,
        tuple(SenseCandidate(c.id, c.part_of_speech, c.gloss) for c in case.candidates),
    )
    try:
        result = await provider.select_sense(request)
    except AIError as error:
        return Outcome(case, None, type(error).__name__, AIUsage(0, 0), UNKNOWN_MODEL)
    return Outcome(case, result.value.selected_meaning_id, None, result.usage, result.model)


def share_correct(outcomes: Sequence[Outcome]) -> float:
    return sum(o.correct for o in outcomes) / len(outcomes) if outcomes else 0.0


def describe_failure(outcome: Outcome) -> Failure:
    case = outcome.case
    if outcome.error is not None:
        return Failure(case.id, f"AI error {outcome.error}")
    return Failure(
        case.id,
        f"expected {case.expected_id}, got {outcome.selected} ({case.word}: {case.sentence})",
    )


async def run(provider: AIProvider, cases: Sequence[SenseCase]) -> SuiteReport:
    outcomes = await run_limited(cases, lambda case: judge_case(provider, case))
    answerable = [o for o in outcomes if o.case.expected_id is not None]
    unanswerable = [o for o in outcomes if o.case.expected_id is None]
    return SuiteReport(
        suite="sense_selection",
        prompt_version=PROMPT_VERSION,
        model=first_model([o.model for o in outcomes]),
        judge_model=None,
        case_count=len(outcomes),
        metrics=[
            Metric("accuracy", share_correct(outcomes), ACCURACY_TARGET),
            Metric(f"accuracy on answerable ({len(answerable)})", share_correct(answerable)),
            Metric(f"accuracy on no-fit cases ({len(unanswerable)})", share_correct(unanswerable)),
            Metric("AI errors", sum(o.error is not None for o in outcomes) / max(len(outcomes), 1)),
        ],
        failures=[describe_failure(o) for o in outcomes if not o.correct],
        usage=sum_usage([o.usage for o in outcomes]),
        judge_usage=AIUsage(0, 0),
    )
