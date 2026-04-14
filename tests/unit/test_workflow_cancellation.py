"""Comprehensive tests for the workflow cancellation mechanism.

Tests cover:
- Session registry: register, cancel, unregister, edge cases
- query_database streaming loop: cancel_event breaks out of the loop
- Thread safety of the registry under concurrent access
"""

import threading
import time
from unittest.mock import patch, MagicMock

import pytest

from server import (
    register_session,
    cancel_session,
    unregister_session,
    _active_sessions,
    _sessions_lock,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure the global session registry is empty before and after each test."""
    with _sessions_lock:
        _active_sessions.clear()
    yield
    with _sessions_lock:
        _active_sessions.clear()


# ---------------------------------------------------------------------------
# Session Registry — register_session
# ---------------------------------------------------------------------------


class TestRegisterSession:
    """Tests for register_session()."""

    def test_register_returns_event(self):
        event = register_session("session-1")
        assert isinstance(event, threading.Event)
        assert not event.is_set()

    def test_register_adds_to_registry(self):
        register_session("session-1")
        with _sessions_lock:
            assert "session-1" in _active_sessions

    def test_register_same_session_cancels_previous(self):
        """Registering the same session ID again sets the old event (cancels it)."""
        first_event = register_session("session-1")
        second_event = register_session("session-1")

        # First event should be set (cancelled)
        assert first_event.is_set()
        # Second event should be fresh (not set)
        assert not second_event.is_set()
        # Registry should hold the new event
        with _sessions_lock:
            assert _active_sessions["session-1"] is second_event

    def test_register_different_sessions_independent(self):
        event_a = register_session("session-a")
        event_b = register_session("session-b")

        assert not event_a.is_set()
        assert not event_b.is_set()
        with _sessions_lock:
            assert len(_active_sessions) == 2

    def test_register_triple_overwrite(self):
        """Three successive registrations: only the latest survives."""
        ev1 = register_session("s")
        ev2 = register_session("s")
        ev3 = register_session("s")

        assert ev1.is_set()
        assert ev2.is_set()
        assert not ev3.is_set()
        with _sessions_lock:
            assert _active_sessions["s"] is ev3


# ---------------------------------------------------------------------------
# Session Registry — cancel_session
# ---------------------------------------------------------------------------


class TestCancelSession:
    """Tests for cancel_session()."""

    def test_cancel_existing_session(self):
        event = register_session("session-1")
        result = cancel_session("session-1")

        assert result is True
        assert event.is_set()

    def test_cancel_removes_from_registry(self):
        register_session("session-1")
        cancel_session("session-1")

        with _sessions_lock:
            assert "session-1" not in _active_sessions

    def test_cancel_nonexistent_session(self):
        result = cancel_session("nonexistent")
        assert result is False

    def test_cancel_already_cancelled_session(self):
        """Cancelling a session that was already cancelled (removed) returns False."""
        register_session("session-1")
        assert cancel_session("session-1") is True
        assert cancel_session("session-1") is False

    def test_cancel_does_not_affect_other_sessions(self):
        event_a = register_session("a")
        event_b = register_session("b")

        cancel_session("a")

        assert event_a.is_set()
        assert not event_b.is_set()
        with _sessions_lock:
            assert "a" not in _active_sessions
            assert "b" in _active_sessions


# ---------------------------------------------------------------------------
# Session Registry — unregister_session
# ---------------------------------------------------------------------------


class TestUnregisterSession:
    """Tests for unregister_session()."""

    def test_unregister_removes_session(self):
        register_session("session-1")
        unregister_session("session-1")

        with _sessions_lock:
            assert "session-1" not in _active_sessions

    def test_unregister_does_not_set_event(self):
        """Unregistering should NOT set the event (normal completion, not cancellation)."""
        event = register_session("session-1")
        unregister_session("session-1")

        assert not event.is_set()

    def test_unregister_nonexistent_is_noop(self):
        """Unregistering a non-existent session should not raise."""
        unregister_session("nonexistent")  # Should not raise

    def test_unregister_idempotent(self):
        register_session("session-1")
        unregister_session("session-1")
        unregister_session("session-1")  # Second call is a no-op

        with _sessions_lock:
            assert "session-1" not in _active_sessions


# ---------------------------------------------------------------------------
# Thread Safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    """Test that the registry is safe under concurrent access."""

    def test_concurrent_register_and_cancel(self):
        """Hammer the registry from multiple threads to check for deadlocks/races."""
        errors = []
        barrier = threading.Barrier(10)

        def worker(session_id):
            try:
                barrier.wait(timeout=5)
                event = register_session(session_id)
                time.sleep(0.001)
                cancel_session(session_id)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=(f"session-{i}",))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0

    def test_concurrent_register_same_session(self):
        """Multiple threads registering the same session ID concurrently."""
        events = []
        barrier = threading.Barrier(5)

        def worker():
            barrier.wait(timeout=5)
            event = register_session("shared-session")
            events.append(event)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Exactly one event should be active (not set), the rest should be set
        assert len(events) == 5
        active_count = sum(1 for e in events if not e.is_set())
        cancelled_count = sum(1 for e in events if e.is_set())
        assert active_count == 1
        assert cancelled_count == 4


# ---------------------------------------------------------------------------
# Integration: cancel_event in query_database streaming loop
# ---------------------------------------------------------------------------


class TestQueryDatabaseCancellation:
    """Test that the cancel_event is checked in the streaming loop."""

    @patch("agent.query_database.create_sql_agent")
    @patch("agent.query_database.create_thread", return_value="thread-1")
    @patch("agent.query_database.save_query_state", return_value="query-1")
    @patch("agent.query_database.clear_debug_files")
    def test_cancel_event_stops_streaming(
        self, mock_clear, mock_save, mock_create_thread, mock_create_agent
    ):
        """When cancel_event is set, the streaming loop should break and yield a cancelled error."""
        from agent.query_database import query_database

        # Create a mock agent that yields multiple chunks
        mock_agent = MagicMock()

        def fake_stream(state, config, stream_mode):
            for i in range(10):
                time.sleep(0.01)
                yield (
                    "custom",
                    {
                        "node_name": f"step_{i}",
                        "node_status": "running",
                        "node_message": f"Step {i}",
                    },
                )
            yield (
                "values",
                {"messages": [], "result": "", "query": "", "thread_id": "thread-1"},
            )

        mock_agent.stream = fake_stream
        mock_create_agent.return_value = mock_agent

        # Create a cancel event and set it after a short delay
        cancel_event = threading.Event()

        def set_after_delay():
            time.sleep(0.03)
            cancel_event.set()

        timer = threading.Thread(target=set_after_delay)
        timer.start()

        events = list(
            query_database(
                "test query",
                stream_updates=True,
                cancel_event=cancel_event,
            )
        )
        timer.join()

        # Should have some status events, then a cancelled error
        types = [e.get("type") if isinstance(e, dict) else None for e in events]
        # The last meaningful event should be the cancellation error
        cancel_events = [
            e for e in events if isinstance(e, dict) and e.get("node") == "cancelled"
        ]
        assert len(cancel_events) == 1
        assert cancel_events[0]["status"] == "cancelled"
        assert cancel_events[0]["message"] == "Workflow cancelled."

    @patch("agent.query_database.create_sql_agent")
    @patch("agent.query_database.create_thread", return_value="thread-1")
    @patch("agent.query_database.save_query_state", return_value="query-1")
    @patch("agent.query_database.clear_debug_files")
    def test_no_cancel_event_completes_normally(
        self, mock_clear, mock_save, mock_create_thread, mock_create_agent
    ):
        """When cancel_event is None, streaming completes normally."""
        from agent.query_database import query_database

        mock_agent = MagicMock()

        def fake_stream(state, config, stream_mode):
            yield ("custom", {"node_name": "step_1", "node_status": "done", "node_message": "OK"})
            yield ("values", {"messages": [], "result": "", "query": "", "thread_id": "thread-1"})

        mock_agent.stream = fake_stream
        mock_create_agent.return_value = mock_agent

        events = list(
            query_database(
                "test query",
                stream_updates=True,
                cancel_event=None,
            )
        )

        # Should have status event + complete event, no cancellation
        cancel_events = [
            e for e in events if isinstance(e, dict) and e.get("node") == "cancelled"
        ]
        assert len(cancel_events) == 0

        complete_events = [
            e for e in events if isinstance(e, dict) and e.get("type") == "complete"
        ]
        assert len(complete_events) == 1

    @patch("agent.query_database.create_sql_agent")
    @patch("agent.query_database.create_thread", return_value="thread-1")
    @patch("agent.query_database.save_query_state", return_value="query-1")
    @patch("agent.query_database.clear_debug_files")
    def test_unset_cancel_event_does_not_interfere(
        self, mock_clear, mock_save, mock_create_thread, mock_create_agent
    ):
        """A cancel_event that is never set should not interfere with normal flow."""
        from agent.query_database import query_database

        mock_agent = MagicMock()

        def fake_stream(state, config, stream_mode):
            yield ("custom", {"node_name": "s1", "node_status": "done", "node_message": "OK"})
            yield ("values", {"messages": [], "result": "", "query": "", "thread_id": "thread-1"})

        mock_agent.stream = fake_stream
        mock_create_agent.return_value = mock_agent

        cancel_event = threading.Event()  # Never set

        events = list(
            query_database(
                "test query",
                stream_updates=True,
                cancel_event=cancel_event,
            )
        )

        cancel_events = [
            e for e in events if isinstance(e, dict) and e.get("node") == "cancelled"
        ]
        assert len(cancel_events) == 0
        assert not cancel_event.is_set()

    @patch("agent.query_database.create_sql_agent")
    @patch("agent.query_database.create_thread", return_value="thread-1")
    @patch("agent.query_database.save_query_state", return_value="query-1")
    @patch("agent.query_database.clear_debug_files")
    def test_cancel_event_pre_set_stops_immediately(
        self, mock_clear, mock_save, mock_create_thread, mock_create_agent
    ):
        """If cancel_event is already set before streaming starts, the loop should exit on the first iteration."""
        from agent.query_database import query_database

        mock_agent = MagicMock()
        chunks_yielded = []

        def fake_stream(state, config, stream_mode):
            for i in range(5):
                chunk = ("custom", {"node_name": f"step_{i}", "node_status": "running", "node_message": f"Step {i}"})
                chunks_yielded.append(chunk)
                yield chunk
            yield ("values", {"messages": [], "result": "", "query": "", "thread_id": "thread-1"})

        mock_agent.stream = fake_stream
        mock_create_agent.return_value = mock_agent

        cancel_event = threading.Event()
        cancel_event.set()  # Pre-set before streaming

        events = list(
            query_database(
                "test query",
                stream_updates=True,
                cancel_event=cancel_event,
            )
        )

        # Should cancel on the first iteration — no status events yielded to caller
        cancel_events = [
            e for e in events if isinstance(e, dict) and e.get("node") == "cancelled"
        ]
        assert len(cancel_events) == 1

        # Only the first chunk should have been consumed from the agent
        # (the cancellation check happens before processing)
        status_events = [
            e for e in events if isinstance(e, dict) and e.get("type") != "error" and e.get("node") != "cancelled"
        ]
        assert len(status_events) == 0


# ---------------------------------------------------------------------------
# Integration: end-to-end register → cancel → streaming stops
# ---------------------------------------------------------------------------


class TestEndToEndCancellation:
    """Test the full flow: register session → start streaming → cancel → streaming stops."""

    @patch("agent.query_database.create_sql_agent")
    @patch("agent.query_database.create_thread", return_value="thread-1")
    @patch("agent.query_database.save_query_state", return_value="query-1")
    @patch("agent.query_database.clear_debug_files")
    def test_register_then_cancel_stops_streaming(
        self, mock_clear, mock_save, mock_create_thread, mock_create_agent
    ):
        """Simulate the real flow: register a session, start streaming, cancel from another thread."""
        from agent.query_database import query_database

        mock_agent = MagicMock()

        def fake_stream(state, config, stream_mode):
            for i in range(50):
                time.sleep(0.01)
                yield ("custom", {"node_name": f"step_{i}", "node_status": "running", "node_message": f"Step {i}"})
            yield ("values", {"messages": [], "result": "", "query": "", "thread_id": "thread-1"})

        mock_agent.stream = fake_stream
        mock_create_agent.return_value = mock_agent

        session_id = "page-session-abc123"
        cancel_event = register_session(session_id)

        # Cancel from another thread after 0.05s
        def cancel_after_delay():
            time.sleep(0.05)
            cancel_session(session_id)

        timer = threading.Thread(target=cancel_after_delay)
        timer.start()

        events = list(
            query_database(
                "test query",
                stream_updates=True,
                cancel_event=cancel_event,
            )
        )
        timer.join()

        # Should have been cancelled mid-stream
        cancel_events = [
            e for e in events if isinstance(e, dict) and e.get("node") == "cancelled"
        ]
        assert len(cancel_events) == 1

        # Should have fewer than 50 status events (was cancelled early)
        status_events = [
            e
            for e in events
            if isinstance(e, dict)
            and e.get("node_name", "").startswith("step_")
        ]
        assert len(status_events) < 50

    def test_register_then_cancel_via_new_page_session(self):
        """Simulate page reload: old session registered, new page calls cancel with old ID."""
        old_session = "csrf-token-old"
        new_session = "csrf-token-new"

        old_event = register_session(old_session)
        assert not old_event.is_set()

        # Simulate new page load calling cancel with old token
        found = cancel_session(old_session)
        assert found is True
        assert old_event.is_set()

        # New session registers cleanly
        new_event = register_session(new_session)
        assert not new_event.is_set()

        with _sessions_lock:
            assert old_session not in _active_sessions
            assert new_session in _active_sessions
