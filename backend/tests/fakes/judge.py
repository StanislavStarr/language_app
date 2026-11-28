from collections.abc import Callable

from app.integrations.ai.provider import AIUsage
from evals.judges import JudgeInput, JudgeResult, JudgeVerdict


def verdict(passed: bool, reason: str = "fine") -> JudgeVerdict:
    return JudgeVerdict(
        definition_matches_meaning=passed,
        definition_fits_level=True,
        example_uses_meaning=True,
        example_natural=True,
        reason=reason,
    )


class FakeJudge:
    def __init__(self, decide: Callable[[JudgeInput], bool] = lambda _item: True) -> None:
        self._decide = decide
        self.judged: list[JudgeInput] = []

    @property
    def model(self) -> str:
        return "fake-judge"

    async def judge(self, item: JudgeInput) -> JudgeResult:
        self.judged.append(item)
        passed = self._decide(item)
        return JudgeResult(verdict(passed, "fine" if passed else "wrong sense"), AIUsage(7, 3))
