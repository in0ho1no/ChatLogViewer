"""Parser utilities for GitHub Copilot Chat transcript JSONL files."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from models import (
    IssueSeverity,
    Message,
    MessageFormat,
    MessageRole,
    ParseIssue,
    Session,
    SessionSourceKind,
    TranscriptEvent,
    TranscriptFile,
)

MESSAGE_EVENT_TYPES: dict[str, MessageRole] = {
    'user.message': MessageRole.USER,
    'assistant.message': MessageRole.ASSISTANT,
}


def parse_transcript_file(file_path: Path) -> TranscriptFile:
    """Parse one transcript JSONL file into raw transcript models."""
    issues: list[ParseIssue] = []
    events: list[TranscriptEvent] = []
    session_id = file_path.stem
    found_session_start = False

    for line_number, raw_line in enumerate(file_path.read_text(encoding='utf-8').splitlines(), start=1):
        if not raw_line.strip():
            continue

        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as error:
            issues.append(
                ParseIssue(
                    severity=IssueSeverity.WARNING,
                    code='invalid-json-line',
                    message=f'Line {line_number} could not be parsed as JSON: {error.msg}',
                    source_path=file_path,
                    line_number=line_number,
                    session_id=session_id,
                    is_skippable=True,
                )
            )
            continue

        event = _parse_event(payload, raw_line, line_number, file_path, session_id)
        if event is None:
            issues.append(
                ParseIssue(
                    severity=IssueSeverity.WARNING,
                    code='invalid-event-shape',
                    message=f'Line {line_number} is missing one or more required event fields.',
                    source_path=file_path,
                    line_number=line_number,
                    session_id=session_id,
                    is_skippable=True,
                )
            )
            continue

        events.append(event)

        if event.event_type != 'session.start':
            continue

        found_session_start = True
        parsed_session_id = _extract_session_id(event.raw_data)
        if parsed_session_id is None:
            issues.append(
                ParseIssue(
                    severity=IssueSeverity.WARNING,
                    code='missing-session-id',
                    message='session.start does not contain data.sessionId.',
                    source_path=file_path,
                    line_number=line_number,
                    session_id=session_id,
                    is_skippable=True,
                )
            )
            continue

        if parsed_session_id != session_id:
            issues.append(
                ParseIssue(
                    severity=IssueSeverity.WARNING,
                    code='session-id-mismatch',
                    message='The transcript file name does not match session.start.data.sessionId.',
                    source_path=file_path,
                    line_number=line_number,
                    session_id=session_id,
                    is_skippable=True,
                )
            )

    if not found_session_start:
        issues.append(
            ParseIssue(
                severity=IssueSeverity.ERROR,
                code='missing-session-start',
                message='The transcript does not contain a session.start event.',
                source_path=file_path,
                session_id=session_id,
                is_skippable=False,
            )
        )

    return TranscriptFile(
        file_path=file_path,
        session_id=session_id,
        events=events,
        issues=issues,
    )


def build_session_from_transcript(transcript: TranscriptFile) -> Session:
    """Normalize one parsed transcript into a session domain model."""
    messages: list[Message] = []
    started_at: datetime | None = None

    for event in transcript.events:
        if event.event_type == 'session.start' and started_at is None:
            started_at = event.timestamp
            continue

        role = MESSAGE_EVENT_TYPES.get(event.event_type)
        if role is None:
            continue

        content = _extract_message_content(event.raw_data)
        if content is None:
            continue

        messages.append(
            Message(
                message_id=_extract_message_id(event.raw_data, event.event_id),
                role=role,
                content=content,
                timestamp=event.timestamp,
                format=MessageFormat.MARKDOWN,
                source_event_ids=[event.event_id],
            )
        )

    oldest_timestamp, latest_timestamp = _calculate_message_range(messages)
    title = _build_session_title(messages, transcript.session_id)

    return Session(
        session_id=transcript.session_id,
        title=title,
        source_kind=SessionSourceKind.TRANSCRIPT,
        source_path=transcript.file_path,
        messages=messages,
        issues=list(transcript.issues),
        started_at=started_at or oldest_timestamp,
        ended_at=latest_timestamp,
        latest_timestamp=latest_timestamp,
        oldest_timestamp=oldest_timestamp,
    )


def parse_transcript_session(file_path: Path) -> Session:
    """Parse one transcript JSONL file directly into a normalized session."""
    return build_session_from_transcript(parse_transcript_file(file_path))


def _parse_event(
    payload: object,
    raw_line: str,
    line_number: int,
    source_path: Path,
    session_id: str,
) -> TranscriptEvent | None:
    if not isinstance(payload, dict):
        return None

    event_id = payload.get('id')
    event_type = payload.get('type')
    raw_data = payload.get('data')
    parent_event_id = payload.get('parentId')

    if not isinstance(event_id, str) or not isinstance(event_type, str) or not isinstance(raw_data, dict):
        return None

    timestamp = _parse_timestamp(payload.get('timestamp'), source_path, line_number, session_id)
    return TranscriptEvent(
        event_id=event_id,
        event_type=event_type,
        timestamp=timestamp,
        parent_event_id=parent_event_id if isinstance(parent_event_id, str) else None,
        raw_data=raw_data,
        raw_line=raw_line,
        line_number=line_number,
    )


def _parse_timestamp(
    raw_value: object,
    source_path: Path,
    line_number: int,
    session_id: str,
) -> datetime | None:
    if not isinstance(raw_value, str) or not raw_value:
        return None

    normalized = raw_value.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _extract_session_id(raw_data: dict[str, object]) -> str | None:
    session_id = raw_data.get('sessionId')
    if isinstance(session_id, str) and session_id:
        return session_id
    return None


def _extract_message_content(raw_data: dict[str, object]) -> str | None:
    for key in ('content', 'message'):
        value = raw_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_message_id(raw_data: dict[str, object], fallback_event_id: str) -> str:
    for key in ('messageId', 'id'):
        value = raw_data.get(key)
        if isinstance(value, str) and value:
            return value
    return fallback_event_id


def _calculate_message_range(messages: list[Message]) -> tuple[datetime | None, datetime | None]:
    timestamps = [message.timestamp for message in messages if message.timestamp is not None]
    if not timestamps:
        return None, None
    return min(timestamps), max(timestamps)


def _build_session_title(messages: list[Message], fallback_session_id: str) -> str:
    for message in messages:
        if message.role is not MessageRole.USER:
            continue
        lines = message.content.splitlines()
        if not lines:
            continue
        first_line = str(lines[0]).strip()
        if not first_line:
            continue
        return first_line[:80]
    return fallback_session_id


__all__ = [
    'MESSAGE_EVENT_TYPES',
    'build_session_from_transcript',
    'parse_transcript_file',
    'parse_transcript_session',
]
