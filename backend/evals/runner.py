import sys
from datetime import UTC, datetime
from pathlib import Path

from app.integrations.ai.openai_provider import OpenAIProvider
from app.integrations.ai.provider import AIProvider

from evals.dataset import ContentCase, SenseCase, read_jsonl
from evals.judges import ContentJudge, OpenAIJudge
from evals.report import REPORTS_DIR, Prices, SuiteReport, render_markdown, write_report
from evals.settings import EvalSettings, get_eval_settings
from evals.suites import meaning_content, sense_selection

SUITE_NAMES = ("sense_selection", "meaning_content")


def prices_from(settings: EvalSettings) -> Prices | None:
    if (
        settings.eval_input_price_per_million is None
        or settings.eval_output_price_per_million is None
    ):
        return None
    return Prices(settings.eval_input_price_per_million, settings.eval_output_price_per_million)


async def run_suite(
    name: str, provider: AIProvider, judge: ContentJudge | None, limit: int | None
) -> SuiteReport:
    if name == "sense_selection":
        return await sense_selection.run(provider, read_jsonl(name, SenseCase, limit))
    if name == "meaning_content":
        if judge is None:
            message = "the meaning_content suite needs a judge"
            raise ValueError(message)
        return await meaning_content.run(provider, judge, read_jsonl(name, ContentCase, limit))
    message = f"unknown suite {name!r}"
    raise ValueError(message)


def publish(report: SuiteReport, prices: Prices | None, directory: Path = REPORTS_DIR) -> Path:
    day = datetime.now(UTC).date()
    path = write_report(report, day, prices, directory)
    sys.stdout.write(render_markdown(report, day, prices))
    return path


async def run_with_settings(name: str, limit: int | None) -> Path:
    settings = get_eval_settings()
    provider = OpenAIProvider.from_settings(settings)
    judge = OpenAIJudge.from_settings(settings) if name == "meaning_content" else None
    report = await run_suite(name, provider, judge, limit)
    return publish(report, prices_from(settings))
