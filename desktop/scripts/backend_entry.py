"""PyInstaller entry point for the packaged backend (issue #47; docs/adr/0016 §5).

``scripts/build-backend.ps1`` freezes this to a ``--onedir`` bundle at
``desktop/backend-dist/deadparrots-backend/``; ``electron-builder.yml`` ships that
tree as ``resources/backend/`` in the installer. It runs the same FastAPI app the
dev shell runs via ``uv run uvicorn deadparrots.app:app`` — the ``--host`` /
``--port`` flags match ``buildBackendCommand``'s frozen branch in
``lib/backend.js``. Not used in development.
"""

from __future__ import annotations

import argparse

import uvicorn

from deadparrots.app import app


def main() -> None:
    parser = argparse.ArgumentParser(prog="deadparrots-backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    # The app object is passed directly (not the "deadparrots.app:app" import
    # string) so uvicorn does not re-import it inside the frozen bundle; reload
    # and multi-worker are off for the same reason.
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
