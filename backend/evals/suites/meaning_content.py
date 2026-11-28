from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.integrations.ai.prompts.meaning_content import PROMPT_VERSION
from app.integrations.ai.provider import (
    AIError,
    AIInvalidOutputError,
    AIProvider,
    AIUsage,
    GenerateMeaningContentRequest,
)

from evals.concurrency import run_limited
from evals.dataset import ContentCase
from evals.judges import JUDGE_PROMPT_VERSION, ContentJudge, JudgeInput
from evals.report import (
    UNKNOWN_MODEL,
    Failure,
    Metric,
    SuiteReport,
    first_model,
    sum_usage,
)

PASS_RATE_TARGET = 0.9
NO_USAGE = AIUsage(0, 0)


@dataclass(frozen=True, slots=True)
class Outcome:
    label: str
    rule_violation: bool
    ai_error: str | None
    judge_passed: bool
    judge_reason: str | None
    usage: AIUsage
    judge_usage: AIUsage
    model: str

    @property
    def passed(self) -> bool:
        return not self.rule_violation and self.ai_error is None and self.judge_passed


def failed_generation(label: str, error: AIError) -> Outcome:
    return Outcome(
        label,
        isinstance(error, AIInvalidOutputError),
        type(error).__name__,
        False,
        None,
        NO_USAGE,
        NO_USAGE,
        UNKNOWN_MODEL,
    )


async def run_one(
    provider: AIProvider, judge: ContentJudge, case: ContentCase, level: str
) -> Outcome:
    label = f"{case.id}/{level}"
    request = GenerateMeaningContentRequest(
        case.word, tuple(case.forms), case.part_of_speech, case.gloss, level
    )
    try:
        generated = await provider.generate_meaning_content(request)
    except AIError as error:
        return failed_generation(label, error)
    item = JudgeInput(
        case.word,
        case.part_of_speech,
        case.gloss,
        level,
        generated.value.definition,
        generated.value.example,
    )
    try:
        judged = await judge.judge(item)
    except AIError as error:
        return Outcome(
            label,
            False,
            f"judge {type(error).__name__}",
            False,
            None,
            generated.usage,
            NO_USAGE,
            generated.model,
        )
    return Outcome(
        label,
        False,
        None,
        judged.verdict.passed,
        judged.verdict.reason,
        generated.usage,
        judged.usage,
        generated.model,
    )


def share(outcomes: Sequence[Outcome], condition: Callable[[Outcome], bool]) -> float:
    return sum(condition(o) for o in outcomes) / len(outcomes) if outcomes else 0.0


def describe_failure(outcome: Outcome) -> Failure:
    if outcome.rule_violation:
        return Failure(outcome.label, f"rules: {outcome.ai_error}")
    if outcome.ai_error is not None:
        return Failure(outcome.label, f"AI error: {outcome.ai_error}")
    return Failure(outcome.label, f"judge: {outcome.judge_reason}")


async def run(
    provider: AIProvider, judge: ContentJudge, cases: Sequence[ContentCase]
) -> SuiteReport:
    pairs = [(case, level) for case in cases for level in case.levels]
    outcomes = await run_limited(pairs, lambda pair: run_one(provider, judge, pair[0], pair[1]))
    judged = [o for o in outcomes if not o.rule_violation and o.ai_error is None]
    return SuiteReport(
        suite="meaning_content",
        prompt_version=f"{PROMPT_VERSION} (judge {JUDGE_PROMPT_VERSION})",
        model=first_model([o.model for o in outcomes]),
        judge_model=judge.model,
        case_count=len(outcomes),
        metrics=[
            Metric(
                "pass rate (rules and judge)", share(outcomes, lambda o: o.passed), PASS_RATE_TARGET
            ),
            Metric("rules pass rate", share(outcomes, lambda o: not o.rule_violation)),
            Metric(
                f"judge pass rate among checked ({len(judged)})",
                share(judged, lambda o: o.judge_passed),
            ),
            Metric(
                "AI and judge errors (not rule violations)",
                share(outcomes, lambda o: o.ai_error is not None and not o.rule_violation),
            ),
        ],
        failures=[describe_failure(o) for o in outcomes if not o.passed],
        usage=sum_usage([o.usage for o in outcomes]),
        judge_usage=sum_usage([o.judge_usage for o in outcomes]),
    )
