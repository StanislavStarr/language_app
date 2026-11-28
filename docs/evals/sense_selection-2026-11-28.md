# Eval: sense_selection (2026-11-28)

- Prompt version: `select_sense-v1`
- Model: `gpt-4o-mini`
- Cases: 40
- Tokens: input 10640, output 697
- Approximate cost: not configured

## Metrics

| Metric | Value | Target | Verdict |
| --- | --- | --- | --- |
| accuracy | 0.750 | 0.85 | BELOW TARGET |
| accuracy on answerable (30) | 0.967 | - | - |
| accuracy on no-fit cases (10) | 0.100 | - | - |
| AI errors | 0.225 | - | - |

## Failures (10)

- `bank-verb`: expected 3, got 1 (bank: He banks with the same company his father used.)
- `bank-none`: AI error AIInvalidOutputError
- `bat-none`: AI error AIInvalidOutputError
- `light-none`: AI error AIInvalidOutputError
- `match-none`: AI error AIInvalidOutputError
- `spring-none`: AI error AIInvalidOutputError
- `row-none`: AI error AIInvalidOutputError
- `spring-none-idiom`: AI error AIInvalidOutputError
- `bat-none-idiom`: AI error AIInvalidOutputError
- `fair-none`: AI error AIInvalidOutputError
