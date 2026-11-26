---
name: run-task
description: Execute one task from docs/plan (e.g. T2.7) end to end — read context, plan, implement, run checks, review, update the plan file. Use when the user says "run task T…", "/run-task T…", or asks to implement a task from the plan.
argument-hint: <task id, e.g. T2.7>
disable-model-invocation: true
---

# Run a plan task

Task id: `$ARGUMENTS`

## 1. Load the task

1. Find the task in `docs/plan/phase-*.md` (`grep -n "### $ARGUMENTS " docs/plan/*.md`).
2. If its status is `[x]` — stop and tell the user. If a previous task in the same phase is `[ ]`
   and this task depends on it — say so and ask whether to continue.
3. Mark the task `[~]` in the plan file.

## 2. Load context (read, do not skim)

- Every doc section listed in **Контекст**.
- `CLAUDE.md` + `backend/CLAUDE.md` and/or `mobile/CLAUDE.md` for the area you touch.
- Skills listed in **Skills**.
- Existing code of the affected modules/slices and one similar existing implementation to mirror
  its conventions.

## 3. Plan

Write a short plan to the user:
- files to create/change (grouped by layer);
- data model / API / migration changes;
- tests you will write (mapped to **Приёмка** and **Тесты**);
- open questions or conflicts with docs.

If the task is estimated ≥ 3 h, or the plan changes a documented decision, or there are open
questions — **wait for the user's confirmation**. Otherwise proceed.

## 4. Implement

- Smallest architecturally correct change. Respect **Не делать**.
- Backend: migration → models → repository → service → schemas → router → jobs → tests.
- Mobile: regenerate API types if the contract changed (`mobile-api-sync`) → entities → features →
  widgets → pages → route file → tests.
- Write tests together with the code, not at the end.

## 5. Verify

- `make backend-check` and/or `make mobile-check` — must be green. Fix, do not skip.
- For migrations: upgrade → downgrade -1 → upgrade.
- For AI features: run the relevant eval suite if prompts/models/retrieval changed (`llm-feature`).
- For UI tasks: list concrete manual checks for the user to do on the phone in Expo Go.

## 6. Review

Run the `code-reviewer` subagent on the diff. Fix every **must-fix** item. Mention **should-fix**
items you deliberately left, with a reason.

## 7. Close

1. Mark the task `[x]` in the plan file and add under it:
   `> Итог: <1–3 sentences: what was done, deviations from the plan, follow-ups>`.
2. If behaviour or a decision changed — update `docs/ARCHITECTURE.md` / `docs/DECISIONS.md`.
3. Out-of-scope ideas → `docs/backlog.md`.
4. Propose a commit message: `<type>(<scope>): <summary> [$ARGUMENTS]`. Commit only if the user asks.
5. Report to the user: what changed, how it was verified, manual checks left for them.
