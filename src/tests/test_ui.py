"""Tests for UI helper formatting."""

from __future__ import annotations

import tkinter as tk
from datetime import UTC, datetime

from models import Message, MessageRole, SessionListItem
from ui import (
    ChatLogViewerApp,
    build_message_heading,
    format_latest_timestamp,
    format_message_timestamp,
    format_warning_flag,
    resolve_sort_by,
    resolve_sort_order,
    sort_session_list_items,
)


def test_format_latest_timestamp_handles_none() -> None:
    """Missing timestamps should render as n/a."""
    assert format_latest_timestamp(None) == 'n/a'


def test_format_latest_timestamp_formats_datetime_seconds() -> None:
    """Aware datetimes should render in JST for the session list."""
    value = datetime(2026, 4, 29, 12, 34, 56, tzinfo=UTC)

    assert format_latest_timestamp(value) == '2026/04/29 21:34:56'


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


def test_resolve_sort_by_supports_japanese_labels() -> None:
    """Japanese sort-by labels should map to internal sort keys."""
    assert resolve_sort_by('タイトル') == 'title'
    assert resolve_sort_by('メッセージ数') == 'message_count'
    assert resolve_sort_by('最終更新') == 'latest'
    assert resolve_sort_by('開始時刻') == 'oldest'
    assert resolve_sort_by('Warnings') == 'warnings'


def test_resolve_sort_order_supports_japanese_labels() -> None:
    """Japanese sort-order labels should map to internal sort keys."""
    assert resolve_sort_order('降順') == 'desc'
    assert resolve_sort_order('昇順') == 'asc'


def test_sort_session_list_items_defaults_to_latest_desc_behavior() -> None:
    """Latest descending should place the newest session first."""
    items = [
        SessionListItem(
            session_id='older',
            display_title='Older',
            message_count=1,
            has_warnings=False,
            latest_timestamp=datetime(2026, 4, 30, 8, 0, 0, tzinfo=UTC),
        ),
        SessionListItem(
            session_id='newer',
            display_title='Newer',
            message_count=1,
            has_warnings=False,
            latest_timestamp=datetime(2026, 4, 30, 9, 0, 0, tzinfo=UTC),
        ),
    ]

    sorted_items = sort_session_list_items(items, sort_by='latest', sort_order='desc')

    assert [item.session_id for item in sorted_items] == ['newer', 'older']


def test_sort_session_list_items_supports_oldest_ascending() -> None:
    """Oldest ascending should place the earliest session first."""
    items = [
        SessionListItem(
            session_id='later',
            display_title='Later',
            message_count=1,
            has_warnings=False,
            oldest_timestamp=datetime(2026, 4, 30, 10, 0, 0, tzinfo=UTC),
        ),
        SessionListItem(
            session_id='earlier',
            display_title='Earlier',
            message_count=1,
            has_warnings=False,
            oldest_timestamp=datetime(2026, 4, 30, 7, 0, 0, tzinfo=UTC),
        ),
    ]

    sorted_items = sort_session_list_items(items, sort_by='oldest', sort_order='asc')

    assert [item.session_id for item in sorted_items] == ['earlier', 'later']


def test_sort_session_list_items_supports_title_ascending() -> None:
    """Title sorting should place entries in case-insensitive order."""
    items = [
        SessionListItem(
            session_id='second',
            display_title='Zulu',
            message_count=1,
            has_warnings=False,
        ),
        SessionListItem(
            session_id='first',
            display_title='alpha',
            message_count=1,
            has_warnings=False,
        ),
    ]

    sorted_items = sort_session_list_items(items, sort_by='title', sort_order='asc')

    assert [item.session_id for item in sorted_items] == ['first', 'second']


def test_sort_session_list_items_supports_message_count_descending() -> None:
    """Message count sorting should place larger sessions first in descending mode."""
    items = [
        SessionListItem(
            session_id='smaller',
            display_title='Smaller',
            message_count=1,
            has_warnings=False,
        ),
        SessionListItem(
            session_id='larger',
            display_title='Larger',
            message_count=3,
            has_warnings=False,
        ),
    ]

    sorted_items = sort_session_list_items(items, sort_by='message_count', sort_order='desc')

    assert [item.session_id for item in sorted_items] == ['larger', 'smaller']


def test_sort_session_list_items_supports_warnings_descending() -> None:
    """Warnings sorting should place warned sessions first in descending mode."""
    items = [
        SessionListItem(
            session_id='clean',
            display_title='Clean',
            message_count=1,
            has_warnings=False,
        ),
        SessionListItem(
            session_id='warned',
            display_title='Warned',
            message_count=1,
            has_warnings=True,
        ),
    ]

    sorted_items = sort_session_list_items(items, sort_by='warnings', sort_order='desc')

    assert [item.session_id for item in sorted_items] == ['warned', 'clean']


def test_heading_sort_updates_sort_state() -> None:
    """Clicking a heading should update the active sort state."""
    root = tk.Tk()
    root.withdraw()
    app = ChatLogViewerApp(root)

    app._handle_heading_sort('title')

    assert app.sort_by_var.get() == 'タイトル'
    assert app.sort_order_var.get() == '昇順'

    app._handle_heading_sort('title')

    assert app.sort_order_var.get() == '降順'
    root.destroy()
