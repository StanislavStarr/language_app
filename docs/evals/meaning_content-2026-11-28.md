# Eval: meaning_content (2026-11-28)

- Prompt version: `meaning_content-v1 (judge content-judge-v1)`
- Model: `gpt-4o-mini`
- Judge model: `gpt-4o-mini` (same as the generation model: self-judging bias is possible)
- Cases: 60
- Tokens: input 35116, output 4137
- Approximate cost: not configured

## Metrics

| Metric | Value | Target | Verdict |
| --- | --- | --- | --- |
| pass rate (rules and judge) | 0.833 | 0.90 | BELOW TARGET |
| rules pass rate | 0.933 | - | - |
| judge pass rate among checked (56) | 0.893 | - | - |
| AI and judge errors (not rule violations) | 0.000 | - | - |

## Failures (10)

- `break-pieces/A2`: judge: The example sentence is not grammatically correct; it should use 'broke' instead of 'break'.
- `break-pieces/B2`: judge: The example sentence has a grammatical error and does not use the correct past tense.
- `key-lock/A2`: judge: The generated definition is somewhat broader than the dictionary definition, as it includes starting a machine, which is not mentioned.
- `plant-living/A2`: rules: AIInvalidOutputError
- `plant-living/B2`: judge: The example does not use 'plant' as a noun, but rather as a verb.
- `plant-put/A2`: rules: AIInvalidOutputError
- `plant-put/B2`: rules: AIInvalidOutputError
- `date-day/B2`: judge: The example inaccurately uses 'date' by including '10th date' instead of simply saying '10th'.
- `mean-intend/A2`: judge: The generated definition is slightly broader than the specific dictionary definition.
- `train-railway/A2`: rules: AIInvalidOutputError
