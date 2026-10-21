import logging
import sys

import pytest

from psd2svg.__main__ import parse_args, resolve_log_level


def _level(monkeypatch: pytest.MonkeyPatch, *flags: str) -> int:
    monkeypatch.setattr(sys, "argv", ["psd2svg", "input.psd", *flags])
    args, _ = parse_args()
    return resolve_log_level(args)


@pytest.mark.parametrize(
    "flags, expected",
    [
        ((), logging.WARNING),
        (("-v",), logging.INFO),
        (("--verbose",), logging.INFO),
        (("-vv",), logging.DEBUG),
        (("-v", "-v", "-v"), logging.DEBUG),
        (("-q",), logging.ERROR),
        (("--quiet",), logging.ERROR),
        (("--loglevel", "debug"), logging.DEBUG),
        (("--loglevel", "ERROR", "-vv"), logging.ERROR),
        (("--loglevel", "bogus"), logging.WARNING),
    ],
)
def test_log_level(
    monkeypatch: pytest.MonkeyPatch, flags: tuple[str, ...], expected: int
) -> None:
    assert _level(monkeypatch, *flags) == expected


def test_verbose_and_quiet_are_mutually_exclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["psd2svg", "input.psd", "-v", "-q"])
    with pytest.raises(SystemExit):
        parse_args()
