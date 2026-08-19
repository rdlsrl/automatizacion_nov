"""CLI for the Industrial Knowledge Loader."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from drilling_knowledge.loader.artifact_registry import LoadPolicy
from drilling_knowledge.loader.orchestrator import LoadOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="knowledge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    load_parser = subparsers.add_parser("load")
    load_parser.add_argument("source")
    _shared_options(load_parser)

    load_las_parser = subparsers.add_parser("load-las")
    load_las_parser.add_argument("folder")
    _shared_options(load_las_parser)
    load_las_parser.add_argument("--recursive", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None, *, orchestrator: LoadOrchestrator | None = None) -> int:
    args = build_parser().parse_args(argv)
    loader = orchestrator or LoadOrchestrator.create_default()
    policy = LoadPolicy(
        max_documents_per_run=args.limit,
        since_date=args.since,
        resume=getattr(args, "resume", False),
        start_after_document_url=getattr(args, "start_after_document_url", None),
        dry_run=args.dry_run,
        fail_fast=args.fail_fast,
        recursive=getattr(args, "recursive", False),
    )
    if args.command == "load":
        summary = loader.load_source(args.source, policy)
    else:
        summary = loader.load_las(Path(args.folder), policy)
    print(
        f"mode={summary.mode} target={summary.target} discovered={summary.discovered} downloaded={summary.downloaded} "
        f"duplicates={summary.duplicates} new_versions={summary.new_versions} dispatched={summary.dispatched} "
        f"failed={summary.failed} gaps_detected={summary.gaps_detected}"
        f" resumed_from={summary.resumed_from_document_url or '-'} last_processed={summary.last_processed_document_url or '-'}"
    )
    return 0 if summary.failed == 0 else 1


def _shared_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=int)
    parser.add_argument("--since")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--start-after-document-url")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")