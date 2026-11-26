#!/usr/bin/env bash
set -uo pipefail

payload="$(cat)"

if command -v jq >/dev/null 2>&1; then
  file_path="$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty')"
else
  file_path="$(printf '%s' "$payload" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))')"
fi

[ -z "$file_path" ] && exit 0
[ -f "$file_path" ] || exit 0

project_dir="${CLAUDE_PROJECT_DIR:-$(pwd)}"

case "$file_path" in
  "$project_dir"/backend/*.py)
    if command -v uv >/dev/null 2>&1 && [ -f "$project_dir/backend/pyproject.toml" ]; then
      (cd "$project_dir/backend" && uv run --quiet ruff format "$file_path" >/dev/null 2>&1 \
        && uv run --quiet ruff check --fix --quiet "$file_path" >/dev/null 2>&1)
    fi
    ;;
  "$project_dir"/mobile/*.ts|"$project_dir"/mobile/*.tsx|"$project_dir"/mobile/*.js|"$project_dir"/mobile/*.mjs|"$project_dir"/mobile/*.json)
    case "$file_path" in
      */schema.d.ts|*/node_modules/*|*/package-lock.json) exit 0 ;;
    esac
    if [ -d "$project_dir/mobile/node_modules" ]; then
      (cd "$project_dir/mobile" && npx --no-install prettier --write --log-level silent "$file_path" >/dev/null 2>&1)
      case "$file_path" in
        *.ts|*.tsx)
          (cd "$project_dir/mobile" && npx --no-install eslint --fix --quiet "$file_path" >/dev/null 2>&1)
          ;;
      esac
    fi
    ;;
esac

exit 0
