"""Tests for Markdown export helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from markdown_export import build_markdown_document, export_markdown_documents
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


def test_export_markdown_documents_writes_unique_files(tmp_path: Path) -> None:
    """Batch export should write one Markdown file per session with unique names."""
    first = Session(
        session_id='session-1',
        title='Same Title',
        source_kind=SessionSourceKind.TRANSCRIPT,
        started_at=datetime(2026, 4, 30, 0, 0, 0, tzinfo=UTC),
    )
    second = Session(
        session_id='session-2',
        title='Same Title',
        source_kind=SessionSourceKind.TRANSCRIPT,
        started_at=datetime(2026, 4, 30, 0, 0, 0, tzinfo=UTC),
    )

    written_paths = export_markdown_documents([first, second], tmp_path)

    assert len(written_paths) == 2
    assert written_paths[0].name == '20260430_090000_Same Title.md'
    assert written_paths[1].name == '20260430_090000_Same Title_2.md'
    assert all(path.exists() for path in written_paths)
