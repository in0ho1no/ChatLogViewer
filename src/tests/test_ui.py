"""Tests for UI helper formatting."""

from __future__ import annotations

from datetime import UTC, datetime

from models import Message, MessageRole
from ui import build_message_heading, format_latest_timestamp, format_message_timestamp, format_warning_flag


def test_format_latest_timestamp_handles_none() -> None:
    """Missing timestamps should render as n/a."""
    assert format_latest_timestamp(None) == 'n/a'


def test_format_latest_timestamp_formats_datetime_seconds() -> None:
    """Datetime values should render as ISO strings without microseconds."""
    value = datetime(2026, 4, 29, 12, 34, 56, tzinfo=UTC)

    assert format_latest_timestamp(value) == '2026-04-29T12:34:56+00:00'


def test_format_warning_flag_uses_yes_no_labels() -> None:
    """Warning flags should render as yes/no strings."""
    assert format_warning_flag(True) == 'yes'
    assert format_warning_flag(False) == 'no'


def test_format_message_timestamp_handles_none() -> None:
    """Missing message timestamps should render as n/a."""
    assert format_message_timestamp(None) == 'n/a'


def test_build_message_heading_includes_role_and_timestamp() -> None:
    """Message headings should distinguish user and assistant messages."""
    message = Message(
        message_id='message-1',
        role=MessageRole.USER,
        content='hello',
        timestamp=datetime(2026, 4, 30, 9, 30, 0, tzinfo=UTC),
    )

    assert build_message_heading(message) == '[USER] 2026-04-30T09:30:00+00:00'
