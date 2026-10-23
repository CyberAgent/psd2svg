"""Tests for timeout_utils module.

This module tests the cross-platform timeout functionality:
- Signal-based timeout on Unix/macOS
- Threading-based timeout on Windows
- Timeout disabled behavior
- Exception propagation
"""

import logging
import signal
import time
from typing import Any

import pytest

from psd2svg.timeout_utils import with_timeout


class TestWithTimeoutBasicBehavior:
    """Tests for basic with_timeout() behavior."""

    def test_warns_at_half_and_three_quarters_of_timeout(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            with_timeout(time.sleep, 1, 0.85)

        warnings = [record.message for record in caplog.records]
        assert any("50%" in message for message in warnings)
        assert any("75%" in message for message in warnings)

    def test_with_timeout_disabled_returns_result(self) -> None:
        """Test with_timeout() executes normally when timeout is disabled (0)."""

        def simple_function(a: int, b: int) -> int:
            return a + b

        # Timeout disabled with 0
        result = with_timeout(simple_function, 0, 10, 20)
        assert result == 30

    def test_with_timeout_negative_returns_result(self) -> None:
        """Test with_timeout() executes normally when timeout is negative."""

        def simple_function(a: int, b: int) -> int:
            return a * b

        # Timeout disabled with negative value
        result = with_timeout(simple_function, -1, 5, 7)
        assert result == 35

    def test_with_timeout_succeeds_within_limit(self) -> None:
        """Test with_timeout() succeeds when function completes quickly."""

        def fast_function(msg: str) -> str:
            return f"Hello, {msg}!"

        result = with_timeout(fast_function, 5, "World")
        assert result == "Hello, World!"

    def test_with_timeout_returns_none(self) -> None:
        """Test with_timeout() correctly returns None when function returns None."""

        def returns_none() -> None:
            return None

        result = with_timeout(returns_none, 5)
        assert result is None

    def test_with_timeout_with_kwargs(self) -> None:
        """Test with_timeout() works with keyword arguments."""

        def function_with_kwargs(x: int, y: int = 0, z: int = 0) -> int:
            return x + y + z

        result = with_timeout(function_with_kwargs, 5, 10, y=20, z=30)
        assert result == 60


class TestWithTimeoutTimeoutBehavior:
    """Tests for timeout enforcement."""

    def test_with_timeout_raises_timeout_error(self) -> None:
        """Test with_timeout() raises TimeoutError when function exceeds timeout."""

        def slow_function() -> None:
            time.sleep(2)

        with pytest.raises(
            TimeoutError, match="PSD conversion timed out after 1 seconds"
        ):
            with_timeout(slow_function, 1)

    def test_with_timeout_error_message_includes_timeout(self) -> None:
        """Test TimeoutError message includes the timeout duration."""

        def slow_function() -> None:
            time.sleep(2)

        # Test with actual timeout
        with pytest.raises(TimeoutError) as exc_info:
            with_timeout(slow_function, 1)

        assert "timed out after 1 seconds" in str(exc_info.value)

    def test_with_timeout_multiple_calls(self) -> None:
        """Test with_timeout() can be called multiple times."""

        def fast_function(x: int) -> int:
            return x * 2

        # Multiple successful calls
        assert with_timeout(fast_function, 5, 10) == 20
        assert with_timeout(fast_function, 5, 20) == 40
        assert with_timeout(fast_function, 5, 30) == 60


class TestWithTimeoutExceptionHandling:
    """Tests for exception propagation through with_timeout()."""

    def test_with_timeout_propagates_value_error(self) -> None:
        """Test with_timeout() propagates ValueError from function."""

        def failing_function() -> None:
            raise ValueError("Test error message")

        with pytest.raises(ValueError, match="Test error message"):
            with_timeout(failing_function, 5)

    def test_with_timeout_propagates_type_error(self) -> None:
        """Test with_timeout() propagates TypeError from function."""

        def failing_function() -> None:
            raise TypeError("Wrong type")

        with pytest.raises(TypeError, match="Wrong type"):
            with_timeout(failing_function, 5)

    def test_with_timeout_propagates_runtime_error(self) -> None:
        """Test with_timeout() propagates RuntimeError from function."""

        def failing_function() -> None:
            raise RuntimeError("Runtime problem")

        with pytest.raises(RuntimeError, match="Runtime problem"):
            with_timeout(failing_function, 5)

    def test_with_timeout_propagates_exception_with_disabled_timeout(self) -> None:
        """Test exceptions are propagated even when timeout is disabled."""

        def failing_function() -> None:
            raise ValueError("Error with no timeout")

        with pytest.raises(ValueError, match="Error with no timeout"):
            with_timeout(failing_function, 0)


class TestWithTimeoutPlatformSpecific:
    """Platform-specific timeout implementation tests."""

    @pytest.mark.skipif(
        not hasattr(signal, "SIGALRM"),
        reason="SIGALRM not available (Windows platform)",
    )
    def test_signal_based_timeout_on_unix(self) -> None:
        """Test with_timeout() uses signal.SIGALRM on Unix/macOS."""

        def slow_function() -> None:
            time.sleep(2)

        # Should use signal-based timeout
        with pytest.raises(TimeoutError):
            with_timeout(slow_function, 1)

    @pytest.mark.skipif(
        not hasattr(signal, "SIGALRM"),
        reason="SIGALRM not available (Windows platform)",
    )
    def test_signal_handler_restored_on_unix(self) -> None:
        """Test signal handler is restored after timeout on Unix/macOS."""

        def fast_function() -> str:
            return "done"

        # Save original handler
        original_handler = signal.signal(signal.SIGALRM, signal.SIG_DFL)

        # Execute with timeout
        result = with_timeout(fast_function, 5)
        assert result == "done"

        # Handler should be restored
        current_handler = signal.signal(signal.SIGALRM, original_handler)
        assert current_handler == original_handler

    @pytest.mark.skipif(
        not hasattr(signal, "SIGALRM"),
        reason="SIGALRM not available (Windows platform)",
    )
    def test_signal_alarm_cleared_on_unix(self) -> None:
        """Test signal.alarm() is cleared after timeout on Unix/macOS."""

        def fast_function() -> str:
            return "done"

        # Execute with timeout
        result = with_timeout(fast_function, 5)
        assert result == "done"

        # Alarm should be cleared (returns 0)
        remaining = signal.alarm(0)
        assert remaining == 0

    @pytest.mark.skipif(
        hasattr(signal, "SIGALRM"),
        reason="Test only for Windows (no SIGALRM)",
    )
    def test_threading_based_timeout_on_windows(self) -> None:
        """Test with_timeout() uses threading fallback on Windows."""

        def slow_function() -> None:
            time.sleep(2)

        # Should use threading-based timeout
        with pytest.raises(TimeoutError):
            with_timeout(slow_function, 1)

    @pytest.mark.skipif(
        hasattr(signal, "SIGALRM"),
        reason="Test only for Windows (no SIGALRM)",
    )
    def test_threading_timeout_returns_result_on_windows(self) -> None:
        """Test threading-based timeout returns result on Windows."""

        def fast_function(x: int) -> int:
            return x * 3

        result = with_timeout(fast_function, 5, 10)
        assert result == 30


class TestWithTimeoutEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_with_timeout_zero_timeout_disables_timeout(self) -> None:
        """Test timeout=0 disables timeout protection."""

        def function_that_takes_time() -> str:
            time.sleep(0.1)
            return "completed"

        # Should complete even though it takes time
        result = with_timeout(function_that_takes_time, 0)
        assert result == "completed"

    def test_with_timeout_very_short_timeout(self) -> None:
        """Test with_timeout() works with very short timeout values."""

        def instant_function() -> str:
            return "instant"

        # Very short timeout but function is faster
        result = with_timeout(instant_function, 1)
        assert result == "instant"

    def test_with_timeout_with_complex_return_type(self) -> None:
        """Test with_timeout() works with complex return types."""

        def returns_dict() -> dict[str, Any]:
            return {"key": "value", "number": 42, "nested": {"inner": "data"}}

        result = with_timeout(returns_dict, 5)
        assert result == {"key": "value", "number": 42, "nested": {"inner": "data"}}

    def test_with_timeout_with_list_return_type(self) -> None:
        """Test with_timeout() works with list return types."""

        def returns_list() -> list[int]:
            return [1, 2, 3, 4, 5]

        result = with_timeout(returns_list, 5)
        assert result == [1, 2, 3, 4, 5]

    def test_with_timeout_function_raising_exception_immediately(self) -> None:
        """Test with_timeout() handles immediate exceptions."""

        def immediate_exception() -> None:
            raise ValueError("Immediate error")

        # Exception should be raised before timeout
        with pytest.raises(ValueError, match="Immediate error"):
            with_timeout(immediate_exception, 5)

    def test_with_timeout_nested_calls(self) -> None:
        """Test with_timeout() can be nested (one timeout inside another)."""

        def inner_function() -> str:
            return "inner result"

        def outer_function() -> str:
            result = with_timeout(inner_function, 2)
            return f"outer: {result}"

        result = with_timeout(outer_function, 5)
        assert result == "outer: inner result"
