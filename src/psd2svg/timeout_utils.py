"""Timeout utilities for resource-limited operations."""

import logging
import signal
import threading
from typing import Any, Callable, TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)


def _warn_about_elapsed_time(finished: threading.Event, timeout_seconds: int) -> None:
    """Warn at the two timeout milestones unless the conversion has finished."""
    for fraction, interval in (
        (50, timeout_seconds / 2),
        (75, timeout_seconds / 4),
    ):
        if finished.wait(interval):
            return
        logger.warning(
            "PSD conversion has used %s%% of its %s-second timeout.",
            fraction,
            timeout_seconds,
        )


def with_timeout(
    func: Callable[..., T], timeout_seconds: int, *args: Any, **kwargs: Any
) -> T:
    """Execute function with timeout protection (cross-platform).

    Args:
        func: Function to execute with timeout.
        timeout_seconds: Maximum execution time in seconds.
            If 0 or negative, no timeout is applied.
        *args: Positional arguments to pass to func.
        **kwargs: Keyword arguments to pass to func.

    Returns:
        Return value from func.

    Raises:
        TimeoutError: If function execution exceeds timeout_seconds.

    Note:
        - On Unix/macOS: Uses signal.SIGALRM for reliable timeout
        - On Windows: Uses threading (may not interrupt native C code)
        - Logs warnings at 50% and 75% of the allotted time.
    """
    if timeout_seconds <= 0:
        return func(*args, **kwargs)

    finished = threading.Event()
    warning_thread = threading.Thread(
        target=_warn_about_elapsed_time,
        args=(finished, timeout_seconds),
        daemon=True,
    )
    warning_thread.start()
    try:
        return _run_with_timeout(func, timeout_seconds, *args, **kwargs)
    finally:
        # A logging handler may block; the daemon monitor must not delay the result.
        finished.set()


def _run_with_timeout(
    func: Callable[..., T], timeout_seconds: int, *args: Any, **kwargs: Any
) -> T:
    """Run the platform-specific timeout after warning monitoring has started."""

    # Try signal-based timeout (Unix/macOS)
    if hasattr(signal, "SIGALRM"):

        def timeout_handler(signum: int, frame: Any) -> None:
            raise TimeoutError(
                f"PSD conversion timed out after {timeout_seconds} seconds. "
                f"File may be complex. "
                f"To process: set PSD2SVG_TIMEOUT={timeout_seconds * 2} environment variable, "  # noqa: E501
                f"or use ResourceLimits(timeout={timeout_seconds * 2}) in Python API."
            )

        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout_seconds)
        try:
            return func(*args, **kwargs)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    else:
        # Fallback for Windows: use threading
        result: list[Any] = [None]
        exception: list[Exception | None] = [None]

        def target() -> None:
            try:
                result[0] = func(*args, **kwargs)
            except Exception as e:
                exception[0] = e

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=timeout_seconds)

        if thread.is_alive():
            raise TimeoutError(
                f"PSD conversion timed out after {timeout_seconds} seconds. "
                f"File may be complex. "
                f"To process: set PSD2SVG_TIMEOUT={timeout_seconds * 2} environment variable, "  # noqa: E501
                f"or use ResourceLimits(timeout={timeout_seconds * 2}) in Python API."
            )
        if exception[0]:
            raise exception[0]
        # After successful thread completion, result[0] contains the return value
        # (which could be None if func returns None). This is correct and matches
        # the return type T, but mypy can't prove this without runtime guarantees.
        return result[0]  # type: ignore[return-value]
