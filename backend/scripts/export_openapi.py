import json
from pathlib import Path

from app.main import create_app

OPENAPI_FILE = Path(__file__).resolve().parents[1] / "openapi.json"


def export_openapi(target: Path = OPENAPI_FILE) -> None:
    schema = create_app().openapi()
    target.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    export_openapi()
