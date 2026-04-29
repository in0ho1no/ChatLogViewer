"""Helpers for building session list view models."""

from __future__ import annotations

from models import Session, SessionListItem


def session_to_list_item(session: Session) -> SessionListItem:
    """Convert one normalized session into a list item."""
    return SessionListItem(
        session_id=session.session_id,
        display_title=session.title,
        message_count=session.message_count,
        has_warnings=session.has_warnings,
        latest_timestamp=session.latest_timestamp,
        oldest_timestamp=session.oldest_timestamp,
    )


def build_session_list_items(sessions: list[Session]) -> list[SessionListItem]:
    """Convert normalized sessions into list items."""
    return [session_to_list_item(session) for session in sessions]


__all__ = ['build_session_list_items', 'session_to_list_item']
