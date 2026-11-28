from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app.integrations.ai.provider import AIUsage

REPORTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "evals"
TOKENS_PER_MILLION = 1_000_000


@dataclass(frozen=True, slots=True)
class Metric:
    name: str
    value: float
    target: float | None = None

    @property
    def passed(self) -> bool | None:
        return None if self.target is None else self.value >= self.target


@dataclass(frozen=True, slots=True)
class Failure:
    case_id: str
    detail: str


@dataclass(frozen=True, slots=True)
class Prices:
    input_per_million: float
    output_per_million: float


UNKNOWN_MODEL = "unknown"
MAX_DETAIL_LENGTH = 200


def sum_usage(usages: Sequence[AIUsage]) -> AIUsage:
    return AIUsage(sum(u.input_tokens for u in usages), sum(u.output_tokens for u in usages))


def first_model(models: Sequence[str]) -> str:
    return next((model for model in models if model != UNKNOWN_MODEL), UNKNOWN_MODEL)


def table_safe(text: str) -> str:
    flat = " ".join(text.split()).replace("|", "/")
    return flat[:MAX_DETAIL_LENGTH]


@dataclass(frozen=True, slots=True)
class SuiteReport:
    suite: str
    prompt_version: str
    model: str
    judge_model: str | None
    case_count: int
    metrics: list[Metric]
    failures: list[Failure]
    usage: AIUsage
    judge_usage: AIUsage


def total_tokens(report: SuiteReport) -> tuple[int, int]:
    return (
        report.usage.input_tokens + report.judge_usage.input_tokens,
        report.usage.output_tokens + report.judge_usage.output_tokens,
    )


def estimated_cost(report: SuiteReport, prices: Prices | None) -> float | None:
    if prices is None:
        return None
    input_tokens, output_tokens = total_tokens(report)
    return (
        input_tokens * prices.input_per_million + output_tokens * prices.output_per_million
    ) / TOKENS_PER_MILLION


def verdict_text(metric: Metric) -> str:
    passed = metric.passed
    return "-" if passed is None else ("OK" if passed else "BELOW TARGET")


def render_markdown(report: SuiteReport, day: date, prices: Prices | None) -> str:
    input_tokens, output_tokens = total_tokens(report)
    cost = estimated_cost(report, prices)
    lines = [
        f"# Eval: {report.suite} ({day.isoformat()})",
        "",
        f"- Prompt version: `{report.prompt_version}`",
        f"- Model: `{report.model}`",
    ]
    if report.judge_model is not None:
        same = " (same as the generation model: self-judging bias is possible)"
        note = same if report.judge_model == report.model else ""
        lines.append(f"- Judge model: `{report.judge_model}`{note}")
    lines += [
        f"- Cases: {report.case_count}",
        f"- Tokens: input {input_tokens}, output {output_tokens}",
        f"- Approximate cost: {'not configured' if cost is None else f'${cost:.4f}'}",
        "",
        "## Metrics",
        "",
        "| Metric | Value | Target | Verdict |",
        "| --- | --- | --- | --- |",
    ]
    for metric in report.metrics:
        target = "-" if metric.target is None else f"{metric.target:.2f}"
        lines.append(f"| {metric.name} | {metric.value:.3f} | {target} | {verdict_text(metric)} |")
    lines += ["", f"## Failures ({len(report.failures)})", ""]
    lines += [
        f"- `{failure.case_id}`: {table_safe(failure.detail)}" for failure in report.failures
    ] or ["None."]
    return "\n".join(lines) + "\n"


def write_report(
    report: SuiteReport, day: date, prices: Prices | None, directory: Path = REPORTS_DIR
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report.suite}-{day.isoformat()}.md"
    path.write_text(render_markdown(report, day, prices), encoding="utf-8")
    return path
