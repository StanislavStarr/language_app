from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from app.integrations.ai.provider import AIUsage
from evals.__main__ import parse_arguments
from evals.report import Failure, Metric, Prices, SuiteReport, estimated_cost, render_markdown
from evals.runner import prices_from, publish, run_suite
from evals.settings import EvalSettings
from tests.fakes.fake_ai_provider import FakeAIProvider
from tests.fakes.judge import FakeJudge

DAY = date(2026, 11, 28)


def sample_report() -> SuiteReport:
    return SuiteReport(
        suite="sense_selection",
        prompt_version="select_sense-v1",
        model="some-model",
        judge_model=None,
        case_count=40,
        metrics=[Metric("accuracy", 0.9, 0.85), Metric("recall", 0.5, 0.8), Metric("info", 0.1)],
        failures=[Failure("bank-river", "expected 2, got 1")],
        usage=AIUsage(1_000_000, 500_000),
        judge_usage=AIUsage(0, 0),
    )


def test_markdown_lists_metrics_verdicts_failures_and_cost() -> None:
    text = render_markdown(sample_report(), DAY, Prices(0.15, 0.60))

    assert text.startswith("# Eval: sense_selection (2026-11-28)")
    assert "`select_sense-v1`" in text
    assert "| accuracy | 0.900 | 0.85 | OK |" in text
    assert "| recall | 0.500 | 0.80 | BELOW TARGET |" in text
    assert "| info | 0.100 | - | - |" in text
    assert "- `bank-river`: expected 2, got 1" in text
    assert "$0.4500" in text


def test_cost_is_not_invented_without_prices() -> None:
    report = sample_report()

    assert estimated_cost(report, None) is None
    assert "not configured" in render_markdown(report, DAY, None)


def test_prices_come_from_settings_only_when_both_are_set() -> None:
    assert prices_from(EvalSettings()) is None
    both = EvalSettings(eval_input_price_per_million=1.0, eval_output_price_per_million=2.0)
    assert prices_from(both) == Prices(1.0, 2.0)


async def test_a_report_is_written_under_the_suite_name_and_date(tmp_path: Path) -> None:
    path = publish(sample_report(), None, tmp_path)

    assert path.parent == tmp_path
    assert path.name.startswith("sense_selection-")
    assert path.suffix == ".md"
    assert "## Metrics" in path.read_text(encoding="utf-8")


async def test_unknown_suite_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown suite"):
        await run_suite("nope", FakeAIProvider(), FakeJudge(), None)


async def test_content_suite_needs_a_judge() -> None:
    with pytest.raises(ValueError, match="needs a judge"):
        await run_suite("meaning_content", FakeAIProvider(), None, None)


def test_command_line_accepts_a_known_suite_and_a_limit() -> None:
    parsed = parse_arguments(["run", "sense_selection", "--limit", "10"])

    assert (parsed.suite, parsed.limit) == ("sense_selection", 10)
    with pytest.raises(SystemExit):
        parse_arguments(["run", "unknown"])


def test_command_line_rejects_an_empty_run() -> None:
    with pytest.raises(SystemExit):
        parse_arguments(["run", "sense_selection", "--limit", "0"])


def test_failure_details_cannot_break_the_markdown_table() -> None:
    report = replace(
        sample_report(), failures=[Failure("x", "bad | cell\nwith newline " + "w" * 400)]
    )

    line = next(
        line for line in render_markdown(report, DAY, None).splitlines() if line.startswith("- `x`")
    )

    assert "|" not in line
    assert "\n" not in line
    assert len(line) < 260


def test_the_report_warns_when_the_judge_is_the_generator() -> None:
    report = replace(sample_report(), judge_model="some-model")

    assert "self-judging" in render_markdown(report, DAY, None)
