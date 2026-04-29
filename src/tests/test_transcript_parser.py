"""Tests for transcript JSONL parsing."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from models import IssueSeverity, MessageRole
from transcript_parser import (
    build_session_from_transcript,
    parse_transcript_file,
    parse_transcript_session,
)


def test_parse_transcript_file_reads_events_and_issues(tmp_path: Path) -> None:
    """The parser should keep valid events and record invalid JSON lines."""
    transcript_path = tmp_path / 'session-1.jsonl'
    transcript_path.write_text(
        '\n'.join(
            [
                '{"type":"session.start","id":"evt-1","timestamp":"2026-04-29T00:00:00Z","data":{"sessionId":"session-1"}}',
                '{"type":"user.message","id":"evt-2","timestamp":"2026-04-29T00:00:01Z","data":{"content":"hello"}}',
                '{"type":"tool.execution_start","id":"evt-3","timestamp":"2026-04-29T00:00:02Z","data":{"name":"read_file"}}',
                '{broken json',
            ]
        ),
        encoding='utf-8',
    )

    transcript = parse_transcript_file(transcript_path)

    assert transcript.session_id == 'session-1'
    assert [event.event_type for event in transcript.events] == [
        'session.start',
        'user.message',
        'tool.execution_start',
    ]
    assert any(issue.code == 'invalid-json-line' for issue in transcript.issues)


def test_build_session_from_transcript_only_materializes_user_and_assistant_messages(tmp_path: Path) -> None:
    """Only user and assistant events should become normalized messages."""
    transcript_path = tmp_path / 'session-1.jsonl'
    transcript_path.write_text(
        '\n'.join(
            [
                '{"type":"session.start","id":"evt-1","timestamp":"2026-04-29T00:00:00Z","data":{"sessionId":"session-1"}}',
                '{"type":"user.message","id":"evt-2","timestamp":"2026-04-29T00:00:01Z","data":{"content":"first question"}}',
                '{"type":"assistant.turn_start","id":"evt-3","timestamp":"2026-04-29T00:00:02Z","data":{}}',
                '{"type":"assistant.message","id":"evt-4","timestamp":"2026-04-29T00:00:03Z","data":{"messageId":"msg-4","content":"first answer"}}',
            ]
        ),
        encoding='utf-8',
    )

    session = parse_transcript_session(transcript_path)

    assert session.title == 'first question'
    assert session.source_path == transcript_path
    assert [message.role for message in session.messages] == [
        MessageRole.USER,
        MessageRole.ASSISTANT,
    ]
    assert session.started_at == datetime(2026, 4, 29, 0, 0, 0, tzinfo=UTC)
    assert session.oldest_timestamp == datetime(2026, 4, 29, 0, 0, 1, tzinfo=UTC)
    assert session.latest_timestamp == datetime(2026, 4, 29, 0, 0, 3, tzinfo=UTC)


def test_parse_transcript_file_records_missing_session_start_as_error(tmp_path: Path) -> None:
    """Transcripts without session.start should keep a non-skippable issue."""
    transcript_path = tmp_path / 'session-1.jsonl'
    transcript_path.write_text(
        '{"type":"user.message","id":"evt-1","timestamp":"2026-04-29T00:00:01Z","data":{"content":"hello"}}',
        encoding='utf-8',
    )

    transcript = parse_transcript_file(transcript_path)

    assert any(
        issue.code == 'missing-session-start' and issue.severity is IssueSeverity.ERROR and issue.is_skippable is False for issue in transcript.issues
    )


def test_parse_transcript_file_records_session_id_mismatch(tmp_path: Path) -> None:
    """The parser should warn when the file stem and session.start disagree."""
    transcript_path = tmp_path / 'session-1.jsonl'
    transcript_path.write_text(
        '{"type":"session.start","id":"evt-1","timestamp":"2026-04-29T00:00:00Z","data":{"sessionId":"other-session"}}',
        encoding='utf-8',
    )

    transcript = parse_transcript_file(transcript_path)

    assert any(issue.code == 'session-id-mismatch' for issue in transcript.issues)


def test_build_session_from_transcript_falls_back_to_session_id_when_no_user_message_exists(tmp_path: Path) -> None:
    """The session title should fall back to the session id when needed."""
    transcript_path = tmp_path / 'session-1.jsonl'
    transcript_path.write_text(
        '\n'.join(
            [
                '{"type":"session.start","id":"evt-1","timestamp":"2026-04-29T00:00:00Z","data":{"sessionId":"session-1"}}',
                '{"type":"assistant.message","id":"evt-2","timestamp":"2026-04-29T00:00:03Z","data":{"content":"answer only"}}',
            ]
        ),
        encoding='utf-8',
    )

    session = build_session_from_transcript(parse_transcript_file(transcript_path))

    assert session.title == 'session-1'
    assert session.messages[0].role is MessageRole.ASSISTANT
