"""Markdown export helpers for chat sessions."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models import MarkdownDocument, MessageRole, Session

TOKYO_TIMEZONE = timezone(timedelta(hours=9), name='JST')
WINDOWS_FORBIDDEN_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def build_markdown_document(session: Session) -> MarkdownDocument:
    """Build one Markdown document for a normalized session."""
    title = session.title.strip()
    filename_title = _sanitize_filename_component(title) or session.session_id
    timestamp = _select_export_timestamp(session)
    timestamp_prefix = timestamp.strftime('%Y%m%d_%H%M%S') if timestamp is not None else session.session_id
    suggested_filename = f'{timestamp_prefix}_{filename_title}.md'

    lines: list[str] = [f'# {title}', '', f'- Session ID: {session.session_id}']

    if session.started_at is not None:
        lines.append(f'- Started: {_format_timestamp(session.started_at)}')
    if session.ended_at is not None:
        lines.append(f'- Ended: {_format_timestamp(session.ended_at)}')

    if session.issues:
        lines.append(f'- Issues: {len(session.issues)}')

    for message in session.messages:
        role_heading = 'User' if message.role is MessageRole.USER else 'Assistant'
        lines.extend(['', f'## {role_heading}'])
        if message.timestamp is not None:
            lines.append(f'_Timestamp: {_format_timestamp(message.timestamp)}_')
            lines.append('')
        lines.append(message.content)

    body = '\n'.join(lines).rstrip() + '\n'
    return MarkdownDocument(
        session_id=session.session_id,
        title=title,
        body=body,
        suggested_filename=suggested_filename,
    )


def export_markdown_documents(sessions: list[Session], output_directory: Path) -> list[Path]:
    """Export multiple sessions as Markdown files into one directory."""
    written_paths: list[Path] = []
    used_names: set[str] = set()

    for session in sessions:
        document = build_markdown_document(session)
        output_path = _build_unique_output_path(output_directory, document.suggested_filename, used_names)
        output_path.write_text(document.body, encoding='utf-8')
        written_paths.append(output_path)

    return written_paths


def _select_export_timestamp(session: Session) -> datetime | None:
    for value in (session.started_at, session.oldest_timestamp, session.latest_timestamp, session.ended_at):
        if isinstance(value, datetime):
            return value.astimezone(TOKYO_TIMEZONE) if value.tzinfo is not None else value
    return None


def _format_timestamp(value: datetime) -> str:
    localized = value.astimezone(TOKYO_TIMEZONE) if value.tzinfo is not None else value
    return localized.strftime('%Y/%m/%d %H:%M:%S')


def _sanitize_filename_component(value: str) -> str:
    normalized = WINDOWS_FORBIDDEN_FILENAME_CHARS.sub('_', value)
    normalized = re.sub(r'\s+', ' ', normalized).strip(' ._')
    return normalized[:80] or 'session'


def _build_unique_output_path(output_directory: Path, filename: str, used_names: set[str]) -> Path:
    candidate = Path(filename)
    stem = candidate.stem
    suffix = candidate.suffix or '.md'
    index = 1
    resolved_name = candidate.name

    while resolved_name.casefold() in used_names or (output_directory / resolved_name).exists():
        index += 1
        resolved_name = f'{stem}_{index}{suffix}'

    used_names.add(resolved_name.casefold())
    return output_directory / resolved_name


__all__ = ['build_markdown_document', 'export_markdown_documents']
