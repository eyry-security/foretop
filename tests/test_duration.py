import asyncio
import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from foretop.cli import _run, build_parser
from foretop.models import Host
from foretop.sinks import Sink
from foretop.sources.base import Source


class BlockingSource(Source):
    async def candidates(self):
        await asyncio.Event().wait()
        yield Host(host="unreachable.example", source="test")


class RecordingSink(Sink):
    def __init__(self):
        self.closed = False

    async def emit(self, host):
        raise AssertionError("blocking source must not emit")

    async def close(self):
        self.closed = True


class DurationParserTests(unittest.TestCase):
    def test_duration_accepts_positive_seconds(self):
        args = build_parser().parse_args(
            ["--scope", "example.com", "--duration", "1.5"]
        )
        self.assertEqual(args.duration, 1.5)

    def test_duration_rejects_non_positive_or_non_finite_values(self):
        for value in ("0", "-1", "nan", "inf"):
            with (
                self.subTest(value=value),
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                build_parser().parse_args(
                    ["--scope", "example.com", "--duration", value]
                )


class DurationRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_duration_stops_cleanly_and_closes_sinks(self):
        sink = RecordingSink()
        args = build_parser().parse_args(
            ["--scope", "example.com", "--duration", "0.01", "--quiet"]
        )

        with (
            patch("foretop.cli._build_source", return_value=BlockingSource()),
            patch("foretop.cli._build_sinks", return_value=[sink]),
        ):
            result = await _run(args)

        self.assertEqual(result, 0)
        self.assertTrue(sink.closed)
