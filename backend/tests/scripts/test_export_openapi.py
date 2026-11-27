import json
from pathlib import Path

from scripts.export_openapi import export_openapi


def test_export_writes_schema_with_api_paths(tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"

    export_openapi(target)

    paths = json.loads(target.read_text())["paths"]
    assert "/api/v1/auth/device" in paths
    assert "/api/v1/users/me" in paths


def test_export_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    export_openapi(first)
    export_openapi(second)

    assert first.read_text() == second.read_text()
