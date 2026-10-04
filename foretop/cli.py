"""Command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import sys

from . import __version__
from .runner import Runner
from .scope import Scope
from .sinks import FileSink, RedisSink, StdoutSink
from .sources import available, get_source


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="foretop",
        description="A pluggable live feed of new hosts for your scope. "
        "Watches a source (certstream first) and hands off in-scope hosts.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  foretop --scope '*.example.com'\n"
            "  foretop --scope example.com --scope example.org | vedette -o live.jsonl\n"
            "  foretop --scope example.com --exclude '*.dev.example.com' -o hosts.jsonl\n"
            "  foretop --scope tesla.com --redis redis://127.0.0.1:6379 --queue vedette:hosts\n"
        ),
    )
    p.add_argument("--version", action="version", version=f"foretop {__version__}")

    p.add_argument(
        "-s", "--source", default="certstream",
        help=f"feed to watch (default: certstream). available: {', '.join(available())}",
    )
    p.add_argument(
        "--scope", action="append", default=[], metavar="PATTERN",
        help="in-scope pattern; repeatable. 'example.com' matches it + subdomains; "
        "globs like '*.example.com' or '*' also work",
    )
    p.add_argument(
        "--exclude", action="append", default=[], metavar="PATTERN",
        help="out-of-scope pattern; repeatable; wins over --scope",
    )
    p.add_argument(
        "--scope-file", metavar="FILE",
        help="file of in-scope patterns, one per line (# comments and blanks ignored)",
    )
    p.add_argument(
        "--exclude-file", metavar="FILE",
        help="file of out-of-scope patterns, one per line",
    )

    # sinks
    p.add_argument("-o", "--output", metavar="FILE", help="append JSONL records to a file")
    p.add_argument("--redis", metavar="URL", help="push hostnames to a Redis list (e.g. redis://127.0.0.1:6379)")
    p.add_argument("--queue", default="vedette:hosts", help="Redis list key to push to (default: vedette:hosts)")
    p.add_argument("--no-redis-dedup", action="store_true", help="don't keep a Redis seen-set across restarts")
    p.add_argument(
        "--json", action="store_true",
        help="print full JSONL records to stdout instead of bare hostnames",
    )

    # limits / behavior
    p.add_argument("--max", type=int, default=None, metavar="N", help="stop after N in-scope hosts")
    p.add_argument("--no-wildcards", action="store_true", help="drop wildcard cert names instead of flattening them")
    p.add_argument("--certstream-url", default=None, help="override the certstream websocket URL")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress stderr progress logs")

    return p


def _build_source(args):
    opts = {"quiet": args.quiet}
    if args.source == "certstream":
        opts["include_wildcards"] = not args.no_wildcards
        if args.certstream_url:
            opts["url"] = args.certstream_url
    return get_source(args.source, **opts)


def _build_sinks(args):
    sinks = []
    if args.redis:
        sinks.append(RedisSink(args.redis, queue=args.queue, dedup=not args.no_redis_dedup))
    if args.output:
        sinks.append(FileSink(args.output))
    if not sinks:
        sinks.append(StdoutSink(json_output=args.json))
    return sinks


def _load_patterns(path: str) -> list[str]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(line)
    return out


async def _run(args) -> int:
    scope_patterns = list(args.scope)
    exclude_patterns = list(args.exclude)
    try:
        if args.scope_file:
            scope_patterns += _load_patterns(args.scope_file)
        if args.exclude_file:
            exclude_patterns += _load_patterns(args.exclude_file)
    except OSError as exc:
        print(f"foretop: {exc}", file=sys.stderr)
        return 2

    try:
        scope = Scope(scope_patterns, exclude_patterns)
    except ValueError as exc:
        print(f"foretop: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        print(f"[foretop] scope: {len(scope_patterns)} pattern(s), "
              f"{len(exclude_patterns)} exclude(s)", file=sys.stderr)

    try:
        source = _build_source(args)
    except ValueError as exc:
        print(f"foretop: {exc}", file=sys.stderr)
        return 2

    sinks = _build_sinks(args)
    runner = Runner(source, scope, sinks, max_items=args.max, quiet=args.quiet)

    try:
        emitted = await runner.run()
    except KeyboardInterrupt:
        emitted = runner.emitted
    if not args.quiet:
        print(
            f"[foretop] done: {emitted} in-scope hosts from "
            f"{runner.seen_total} candidates",
            file=sys.stderr,
        )
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
