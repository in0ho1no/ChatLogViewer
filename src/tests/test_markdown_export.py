"""Tests for Markdown export helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from markdown_export import build_markdown_document
from models import Message, MessageRole, Session, SessionSourceKind


def test_build_markdown_document_includes_messages_and_metadata() -> None:
    """Exported Markdown should include title, metadata, and message bodies."""
    session = Session(
        session_id='session-1',
        title='Review: feature/export?',
        source_kind=SessionSourceKind.TRANSCRIPT,
        messages=[
            Message(
                message_id='m1',
                role=MessageRole.USER,
                content='First prompt',
                timestamp=datetime(2026, 4, 30, 0, 0, 0, tzinfo=UTC),
            ),
            Message(
                message_id='m2',
                role=MessageRole.ASSISTANT,
                content='Reply body',
                timestamp=datetime(2026, 4, 30, 0, 1, 0, tzinfo=UTC),
            ),
        ],
        started_at=datetime(2026, 4, 30, 0, 0, 0, tzinfo=UTC),
        ended_at=datetime(2026, 4, 30, 0, 1, 0, tzinfo=UTC),
        oldest_timestamp=datetime(2026, 4, 30, 0, 0, 0, tzinfo=UTC),
        latest_timestamp=datetime(2026, 4, 30, 0, 1, 0, tzinfo=UTC),
    )

    document = build_markdown_document(session)

    assert document.suggested_filename == '20260430_090000_Review_ feature_export.md'
    assert '# Review: feature/export?' in document.body
    assert '- Session ID: session-1' in document.body
    assert '- Started: 2026/04/30 09:00:00' in document.body
    assert '## User' in document.body
    assert 'First prompt' in document.body
    assert '## Assistant' in document.body
    assert 'Reply body' in document.body
