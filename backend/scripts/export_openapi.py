"""Write the OpenAPI schema to backend/openapi.json (input for the frontend type generator)."""

import json
from pathlib import Path

from app.main import create_app

if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "openapi.json"
    out.write_text(json.dumps(create_app().openapi(), indent=2) + "\n")
    print(f"wrote {out}")
