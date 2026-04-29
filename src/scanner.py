"""Transcript scanning utilities."""

from __future__ import annotations

import os
from pathlib import Path

from models import ParseIssue, Session
from transcript_parser import parse_transcript_session

TRANSCRIPTS_GLOB = 'workspaceStorage/*/GitHub.copilot-chat/transcripts/*.jsonl'


def get_default_user_data_root() -> Path:
    """Return the default VS Code user data root for the current user."""
    appdata = os.environ.get('APPDATA')
    if not appdata:
        msg = 'APPDATA environment variable is not set.'
        raise RuntimeError(msg)
    return Path(appdata) / 'Code' / 'User'


def find_transcript_files(root_dir: Path) -> list[Path]:
    """Find GitHub Copilot Chat transcript files under the given root directory."""
    return sorted(root_dir.glob(TRANSCRIPTS_GLOB))


def scan_sessions(root_dir: Path) -> list[Session]:
    """Parse all transcript files found under the given root directory."""
    sessions: list[Session] = []
    for transcript_path in find_transcript_files(root_dir):
        sessions.append(parse_transcript_session(transcript_path))
    return sessions


def summarize_scan(sessions: list[Session]) -> tuple[int, int]:
    """Return counts for scanned sessions and sessions with warnings."""
    warning_count = sum(1 for session in sessions if session.has_warnings)
    return len(sessions), warning_count


def collect_scan_issues(sessions: list[Session]) -> list[ParseIssue]:
    """Collect issues emitted by scanned sessions."""
    issues: list[ParseIssue] = []
    for session in sessions:
        issues.extend(session.issues)
    return issues


__all__ = [
    'TRANSCRIPTS_GLOB',
    'collect_scan_issues',
    'find_transcript_files',
    'get_default_user_data_root',
    'scan_sessions',
    'summarize_scan',
]
