"""Headless entrypoint for the ResearchMap pipeline.

Currently exposes:

    python -m backend.cli ingest [--query STR] [--limit N] [--source auto|live|seed]

Emits validated Paper JSON to stdout. This is the phase-1 demo command.
"""

from __future__ import annotations

import argparse
import json
import sys

from backend.app.config import get_settings
from backend.app.ingestion.pipeline import run_ingestion


def _cmd_ingest(args: argparse.Namespace) -> int:
    papers = run_ingestion(query=args.query, limit=args.limit, prefer=args.source)
    payload = {
        "query": args.query,
        "source_preference": args.source,
        "count": len(papers),
        "papers": [json.loads(p.model_dump_json()) for p in papers],
    }
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def _cmd_config(_args: argparse.Namespace) -> int:
    settings = get_settings()
    print(repr(settings))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="researchmap")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ing = sub.add_parser("ingest", help="Ingest papers matching a query.")
    ing.add_argument("--query", default="", help="Free-text search query. Empty = return all seed papers.")
    ing.add_argument("--limit", type=int, default=50)
    ing.add_argument("--source", choices=("auto", "live", "seed"), default="auto")
    ing.set_defaults(func=_cmd_ingest)

    cfg = sub.add_parser("config", help="Print resolved runtime config (no secrets).")
    cfg.set_defaults(func=_cmd_config)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
