"""Tests for the shared data models."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from models import (
    DisplayMessage,
    ExportBatch,
    IssueSeverity,
    Message,
    MessageFormat,
    MessageRole,
    ParseIssue,
    Session,
    SessionMetadataSource,
    SessionSourceKind,
    TranscriptEvent,
    TranscriptFile,
)


def test_session_supports_independent_mutable_defaults() -> None:
    """Mutable default fields should not leak across session instances."""
    first = Session(
        session_id='session-1',
        title='First session',
        source_kind=SessionSourceKind.TRANSCRIPT,
    )
    second = Session(
        session_id='session-2',
        title='Second session',
        source_kind=SessionSourceKind.TRANSCRIPT,
    )

    first.messages.append(
        Message(
            message_id='message-1',
            role=MessageRole.USER,
            content='hello',
            timestamp=datetime(2026, 4, 29, tzinfo=UTC),
            format=MessageFormat.PLAIN_TEXT,
        )
    )

    assert first.message_count == 1
    assert second.message_count == 0


def test_session_rejects_invalid_timestamp_order() -> None:
    """The session model should reject inverted timestamp ranges."""
    with pytest.raises(ValueError, match='oldest_timestamp'):
        Session(
            session_id='session-1',
            title='Broken session',
            source_kind=SessionSourceKind.TRANSCRIPT,
            oldest_timestamp=datetime(2026, 4, 30, tzinfo=UTC),
            latest_timestamp=datetime(2026, 4, 29, tzinfo=UTC),
        )


def test_transcript_models_capture_file_and_event_information() -> None:
    """Transcript models should retain parsed event and issue details."""
    event = TranscriptEvent(
        event_id='event-1',
        event_type='assistant.message',
        timestamp=datetime(2026, 4, 29, 12, 0, tzinfo=UTC),
        parent_event_id=None,
        raw_data={'content': 'hello'},
        raw_line='{"type": "assistant.message"}',
        line_number=2,
    )
    transcript = TranscriptFile(
        file_path=Path('transcripts/session-1.jsonl'),
        session_id='session-1',
        events=[event],
        issues=[
            ParseIssue(
                severity=IssueSeverity.WARNING,
                code='missing-timestamp',
                message='A later event is missing a timestamp.',
                is_skippable=True,
            )
        ],
    )

    assert transcript.events[0].event_type == 'assistant.message'
    assert transcript.issues[0].severity is IssueSeverity.WARNING


def test_session_has_warnings_when_warning_issue_exists() -> None:
    """Warning and error issues should mark a session as having warnings."""
    session = Session(
        session_id='session-1',
        title='Warning session',
        source_kind=SessionSourceKind.TRANSCRIPT,
        issues=[
            ParseIssue(
                severity=IssueSeverity.WARNING,
                code='parse-warning',
                message='One line could not be parsed.',
            )
        ],
    )

    assert session.has_warnings is True


def test_auxiliary_models_validate_required_fields() -> None:
    """Auxiliary models should be constructible with their required fields."""
    metadata = SessionMetadataSource(session_id='session-1')
    detail_message = DisplayMessage(role_label='AI', content='Hello', use_monospace=False)
    export = ExportBatch(session_ids=['session-1'], output_directory=Path('exports'))

    assert metadata.session_id == 'session-1'
    assert detail_message.role_label == 'AI'
    assert export.output_directory == Path('exports')
