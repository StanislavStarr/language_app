from functools import lru_cache

from app.core.config import Settings


class EvalSettings(Settings):
    eval_judge_model: str | None = None
    eval_input_price_per_million: float | None = None
    eval_output_price_per_million: float | None = None


@lru_cache
def get_eval_settings() -> EvalSettings:
    return EvalSettings()
