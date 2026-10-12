"""Dump the live OpenAPI spec to stdout — source for the frontend's typed client.

`python -m lineage.api.export_openapi > ../frontend/openapi.json`. Importing the
app is enough to build the schema; no DB/lifespan needed (app.openapi() only reads
route definitions). Wired as `npm run api:spec`."""

from __future__ import annotations

import json

from .main import app


def main() -> None:
    print(json.dumps(app.openapi(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
