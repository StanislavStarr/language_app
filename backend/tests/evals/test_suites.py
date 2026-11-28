import pytest
from app.integrations.ai.provider import (
    AIInvalidOutputError,
    AIUnavailableError,
    GenerateMeaningContentRequest,
    SelectSenseRequest,
)
from app.integrations.ai.schemas.meaning_content import MeaningContentOutput
from app.integrations.ai.schemas.sense_selection import SenseSelectionOutput
from evals.dataset import ContentCase, SenseCase, read_jsonl
from evals.judges import JudgeInput, JudgeResult
from evals.suites import meaning_content, sense_selection
from tests.fakes.fake_ai_provider import FakeAIProvider
from tests.fakes.judge import FakeJudge

CASES = read_jsonl("sense_selection", SenseCase)
BY_SENTENCE = {(case.word, case.sentence, len(case.candidates)): case for case in CASES}


def oracle(request: SelectSenseRequest) -> SenseSelectionOutput:
    case = BY_SENTENCE[(request.word, request.sentence, len(request.candidates))]
    return SenseSelectionOutput(
        selected_meaning_id=case.expected_id,
        contextual_translation=None if case.expected_id is None else "слово",
        confidence=0.9,
    )


def always_first(request: SelectSenseRequest) -> SenseSelectionOutput:
    return SenseSelectionOutput(
        selected_meaning_id=request.candidates[0].id, contextual_translation="слово", confidence=0.5
    )


async def test_a_perfect_selector_scores_one() -> None:
    report = await sense_selection.run(FakeAIProvider(sense=oracle), CASES)

    accuracy = report.metrics[0]
    assert (accuracy.name, accuracy.value, accuracy.passed) == ("accuracy", 1.0, True)
    assert report.failures == []
    assert report.case_count == 40
    assert report.usage.input_tokens == 400
    assert report.model == "fake-model"


async def test_a_naive_selector_misses_the_target_and_lists_its_failures() -> None:
    report = await sense_selection.run(FakeAIProvider(sense=always_first), CASES)

    accuracy, answerable, no_fit, errors = report.metrics
    assert accuracy.passed is False
    assert 0 < accuracy.value < 0.5
    assert no_fit.value == 0.0
    assert answerable.value > no_fit.value
    assert errors.value == 0.0
    assert len(report.failures) == round((1 - accuracy.value) * 40)
    assert any(failure.case_id == "bank-river" for failure in report.failures)


async def test_ai_errors_count_as_failures_not_crashes() -> None:
    report = await sense_selection.run(FakeAIProvider(error=AIUnavailableError("down")), CASES[:5])

    assert report.metrics[0].value == 0.0
    assert report.metrics[3].value == 1.0
    assert report.failures[0].detail == "AI error AIUnavailableError"
    assert report.model == "unknown"


CONTENT_CASES = read_jsonl("meaning_content", ContentCase, 4)
GOOD = MeaningContentOutput(definition="A good definition here.", example="A good bank example.")


async def test_content_passes_when_rules_and_judge_agree() -> None:
    provider = FakeAIProvider(content=GOOD)
    judge = FakeJudge()

    report = await meaning_content.run(provider, judge, CONTENT_CASES)

    assert report.case_count == 8
    assert [m.value for m in report.metrics] == [1.0, 1.0, 1.0, 0.0]
    assert report.metrics[0].passed is True
    assert report.judge_model == "fake-judge"
    assert (report.usage.input_tokens, report.judge_usage.input_tokens) == (80, 56)
    assert {item.cefr_level for item in judge.judged} == {"A2", "B2"}


async def test_judge_rejections_lower_the_pass_rate_and_are_explained() -> None:
    def reject_b2(item: JudgeInput) -> bool:
        return item.cefr_level != "B2"

    report = await meaning_content.run(
        FakeAIProvider(content=GOOD), FakeJudge(reject_b2), CONTENT_CASES
    )

    assert report.metrics[0].value == 0.5
    assert report.metrics[0].passed is False
    assert report.metrics[1].value == 1.0
    assert report.metrics[2].value == 0.5
    assert {failure.detail for failure in report.failures} == {"judge: wrong sense"}
    assert all(failure.case_id.endswith("/B2") for failure in report.failures)


async def test_rule_violations_are_failures_and_skip_the_judge() -> None:
    def broken(_request: GenerateMeaningContentRequest) -> MeaningContentOutput:
        raise AIInvalidOutputError("definition contains the word")

    judge = FakeJudge()

    report = await meaning_content.run(FakeAIProvider(content=broken), judge, CONTENT_CASES)

    assert report.metrics[0].value == 0.0
    assert report.metrics[1].value == 0.0
    assert report.metrics[3].value == 0.0
    assert judge.judged == []
    assert report.failures[0].detail == "rules: AIInvalidOutputError"


async def test_outages_are_not_counted_as_rule_violations() -> None:
    provider = FakeAIProvider(error=AIUnavailableError("down"))

    report = await meaning_content.run(provider, FakeJudge(), CONTENT_CASES)

    assert report.metrics[1].value == 1.0
    assert report.metrics[3].value == 1.0
    assert report.failures[0].detail == "AI error: AIUnavailableError"


async def test_judge_failures_are_reported_as_errors_not_as_rejections() -> None:
    class BrokenJudge(FakeJudge):
        async def judge(self, _item: JudgeInput) -> JudgeResult:
            raise AIInvalidOutputError("bad verdict")

    report = await meaning_content.run(FakeAIProvider(content=GOOD), BrokenJudge(), CONTENT_CASES)

    assert report.metrics[0].value == 0.0
    assert report.metrics[3].value == 1.0
    assert report.failures[0].detail == "AI error: judge AIInvalidOutputError"


@pytest.mark.parametrize("limit", [1, 2])
async def test_limit_shrinks_the_run(limit: int) -> None:
    cases = read_jsonl("meaning_content", ContentCase, limit)

    report = await meaning_content.run(FakeAIProvider(content=GOOD), FakeJudge(), cases)

    assert report.case_count == limit * 2
