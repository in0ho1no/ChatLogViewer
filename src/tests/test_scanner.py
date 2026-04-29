"""Tests for transcript scanning and session list conversion."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from models import IssueSeverity, ParseIssue, Session, SessionSourceKind
from scanner import (
    collect_scan_issues,
    find_transcript_files,
    get_default_user_data_root,
    scan_sessions,
    summarize_scan,
)
from session_list import build_session_list_items, session_to_list_item


def test_find_transcript_files_discovers_copilot_transcripts(tmp_path: Path) -> None:
    """The scanner should find transcript files in the expected directory layout."""
    transcript_dir = tmp_path / 'workspaceStorage' / 'abc123' / 'GitHub.copilot-chat' / 'transcripts'
    transcript_dir.mkdir(parents=True)
    transcript_path = transcript_dir / 'session-1.jsonl'
    transcript_path.write_text('', encoding='utf-8')

    found_files = find_transcript_files(tmp_path)

    assert found_files == [transcript_path]


def test_scan_sessions_parses_all_found_transcripts(tmp_path: Path) -> None:
    """The scanner should parse all transcript files under the root directory."""
    transcript_dir = tmp_path / 'workspaceStorage' / 'abc123' / 'GitHub.copilot-chat' / 'transcripts'
    transcript_dir.mkdir(parents=True)
    (transcript_dir / 'session-1.jsonl').write_text(
        '\n'.join(
            [
                '{"type":"session.start","id":"evt-1","timestamp":"2026-04-29T00:00:00Z","data":{"sessionId":"session-1"}}',
                '{"type":"user.message","id":"evt-2","timestamp":"2026-04-29T00:00:01Z","data":{"content":"hello"}}',
            ]
        ),
        encoding='utf-8',
    )
    (transcript_dir / 'session-2.jsonl').write_text(
        '{"type":"session.start","id":"evt-1","timestamp":"2026-04-29T01:00:00Z","data":{"sessionId":"session-2"}}',
        encoding='utf-8',
    )

    sessions = scan_sessions(tmp_path)

    assert [session.session_id for session in sessions] == ['session-1', 'session-2']


def test_session_list_conversion_preserves_summary_fields() -> None:
    """Session list items should reflect the session summary fields."""
    session = Session(
        session_id='session-1',
        title='First session',
        source_kind=SessionSourceKind.TRANSCRIPT,
        issues=[
            ParseIssue(
                severity=IssueSeverity.WARNING,
                code='warning',
                message='warning message',
            )
        ],
        oldest_timestamp=datetime(2026, 4, 29, 0, 0, 0, tzinfo=UTC),
        latest_timestamp=datetime(2026, 4, 29, 0, 1, 0, tzinfo=UTC),
    )

    item = session_to_list_item(session)

    assert item.display_title == 'First session'
    assert item.has_warnings is True
    assert item.latest_timestamp == datetime(2026, 4, 29, 0, 1, 0, tzinfo=UTC)


def test_collect_scan_issues_and_summary_aggregate_sessions() -> None:
    """Scanner helpers should summarize sessions and collect their issues."""
    sessions = [
        Session(
            session_id='session-1',
            title='One',
            source_kind=SessionSourceKind.TRANSCRIPT,
            issues=[],
        ),
        Session(
            session_id='session-2',
            title='Two',
            source_kind=SessionSourceKind.TRANSCRIPT,
            issues=[
                ParseIssue(
                    severity=IssueSeverity.WARNING,
                    code='warning',
                    message='warning message',
                )
            ],
        ),
    ]

    session_count, warning_count = summarize_scan(sessions)
    issues = collect_scan_issues(sessions)
    items = build_session_list_items(sessions)

    assert session_count == 2
    assert warning_count == 1
    assert len(issues) == 1
    assert len(items) == 2


def test_get_default_user_data_root_uses_appdata(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default scan root should be resolved from APPDATA."""
    monkeypatch.setenv('APPDATA', r'C:\Users\test\AppData\Roaming')

    assert get_default_user_data_root() == Path(r'C:\Users\test\AppData\Roaming') / 'Code' / 'User'


def test_get_default_user_data_root_requires_appdata(monkeypatch: pytest.MonkeyPatch) -> None:
    """The scanner should fail fast when APPDATA is unavailable."""
    monkeypatch.delenv('APPDATA', raising=False)

    with pytest.raises(RuntimeError, match='APPDATA'):
        get_default_user_data_root()
