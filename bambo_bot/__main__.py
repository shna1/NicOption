from __future__ import annotations

import argparse
import logging

from .config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="NI Option local options dashboard")
    parser.add_argument("--web", action="store_true", help="run the local dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="dashboard bind address")
    parser.add_argument("--port", type=int, default=8765, help="dashboard port")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings()
    settings.validate()
    from .web import serve_dashboard

    serve_dashboard(settings, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
