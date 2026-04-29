"""Chat log viewer data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

type JsonObject = dict[str, object]


class SessionSourceKind(StrEnum):
    """Represents the primary source used to restore a session."""

    TRANSCRIPT = 'transcript'
    LEGACY_SQLITE = 'legacy_sqlite'


class MessageRole(StrEnum):
    """Represents the author of a message."""

    USER = 'user'
    ASSISTANT = 'assistant'


class MessageFormat(StrEnum):
    """Represents how a message body should be interpreted."""

    PLAIN_TEXT = 'plain_text'
    MARKDOWN = 'markdown'


class IssueSeverity(StrEnum):
    """Represents the severity of a parse or validation issue."""

    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'


@dataclass(slots=True)
class ParseIssue:
    """Describes a problem found while loading or normalizing data."""

    severity: IssueSeverity
    code: str
    message: str
    source_path: Path | None = None
    line_number: int | None = None
    session_id: str | None = None
    is_skippable: bool = True

    def __post_init__(self) -> None:
        """Validate the required fields."""
        if not self.code:
            msg = 'code must not be empty'
            raise ValueError(msg)
        if not self.message:
            msg = 'message must not be empty'
            raise ValueError(msg)


@dataclass(slots=True)
class TranscriptEvent:
    """Represents one event line from a transcript JSONL file."""

    event_id: str
    event_type: str
    timestamp: datetime | None
    parent_event_id: str | None
    raw_data: JsonObject
    raw_line: str
    line_number: int

    def __post_init__(self) -> None:
        """Validate the required fields."""
        if not self.event_id:
            msg = 'event_id must not be empty'
            raise ValueError(msg)
        if not self.event_type:
            msg = 'event_type must not be empty'
            raise ValueError(msg)
        if self.line_number < 1:
            msg = 'line_number must be greater than zero'
            raise ValueError(msg)


@dataclass(slots=True)
class TranscriptFile:
    """Represents one transcript file and the issues found while loading it."""

    file_path: Path
    session_id: str
    events: list[TranscriptEvent] = field(default_factory=list)
    issues: list[ParseIssue] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate the required fields."""
        if not self.session_id:
            msg = 'session_id must not be empty'
            raise ValueError(msg)


@dataclass(slots=True)
class SessionMetadataSource:
    """Represents auxiliary session metadata loaded from JSON files."""

    session_id: str
    title: str | None = None
    first_user_message: str | None = None
    workspace_folder: str | None = None
    repository_path: str | None = None
    raw_payload: JsonObject = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate the required fields."""
        if not self.session_id:
            msg = 'session_id must not be empty'
            raise ValueError(msg)


@dataclass(slots=True)
class LegacySessionSource:
    """Represents one legacy session record loaded from SQLite."""

    storage_key: str
    raw_json: str
    session_id: str | None = None
    parsed_payload: JsonObject | None = None
    issues: list[ParseIssue] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate the required fields."""
        if not self.storage_key:
            msg = 'storage_key must not be empty'
            raise ValueError(msg)
        if not self.raw_json:
            msg = 'raw_json must not be empty'
            raise ValueError(msg)


@dataclass(slots=True)
class SessionMetadata:
    """Represents normalized auxiliary metadata for one session."""

    custom_title: str | None = None
    first_user_message: str | None = None
    workspace_folder: str | None = None
    repository_path: str | None = None
    raw_sources: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Message:
    """Represents one normalized chat message."""

    message_id: str
    role: MessageRole
    content: str
    timestamp: datetime | None
    format: MessageFormat = MessageFormat.PLAIN_TEXT
    source_event_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate the required fields."""
        if not self.message_id:
            msg = 'message_id must not be empty'
            raise ValueError(msg)
        if not self.content:
            msg = 'content must not be empty'
            raise ValueError(msg)


@dataclass(slots=True)
class Session:
    """Represents one normalized chat session."""

    session_id: str
    title: str
    source_kind: SessionSourceKind
    messages: list[Message] = field(default_factory=list)
    metadata: SessionMetadata = field(default_factory=SessionMetadata)
    issues: list[ParseIssue] = field(default_factory=list)
    started_at: datetime | None = None
    ended_at: datetime | None = None
    latest_timestamp: datetime | None = None
    oldest_timestamp: datetime | None = None

    def __post_init__(self) -> None:
        """Validate session invariants."""
        if not self.session_id:
            msg = 'session_id must not be empty'
            raise ValueError(msg)
        if not self.title:
            msg = 'title must not be empty'
            raise ValueError(msg)
        if self.oldest_timestamp and self.latest_timestamp and self.oldest_timestamp > self.latest_timestamp:
            msg = 'oldest_timestamp must be less than or equal to latest_timestamp'
            raise ValueError(msg)

    @property
    def message_count(self) -> int:
        """Return the number of normalized messages."""
        return len(self.messages)

    @property
    def has_warnings(self) -> bool:
        """Return whether the session contains warning or error issues."""
        return any(issue.severity in {IssueSeverity.WARNING, IssueSeverity.ERROR} for issue in self.issues)


@dataclass(slots=True)
class SessionListItem:
    """Represents one entry in the session list pane."""

    session_id: str
    display_title: str
    message_count: int
    has_warnings: bool
    latest_timestamp: datetime | None = None
    oldest_timestamp: datetime | None = None

    def __post_init__(self) -> None:
        """Validate the required fields."""
        if not self.session_id:
            msg = 'session_id must not be empty'
            raise ValueError(msg)
        if not self.display_title:
            msg = 'display_title must not be empty'
            raise ValueError(msg)
        if self.message_count < 0:
            msg = 'message_count must be zero or greater'
            raise ValueError(msg)


@dataclass(slots=True)
class DisplayWarning:
    """Represents a user-facing warning shown in the UI."""

    code: str
    message: str

    def __post_init__(self) -> None:
        """Validate the required fields."""
        if not self.code:
            msg = 'code must not be empty'
            raise ValueError(msg)
        if not self.message:
            msg = 'message must not be empty'
            raise ValueError(msg)


@dataclass(slots=True)
class DisplayMessage:
    """Represents one message as rendered in the detail pane."""

    role_label: str
    content: str
    use_monospace: bool
    timestamp_text: str | None = None

    def __post_init__(self) -> None:
        """Validate the required fields."""
        if not self.role_label:
            msg = 'role_label must not be empty'
            raise ValueError(msg)
        if not self.content:
            msg = 'content must not be empty'
            raise ValueError(msg)


@dataclass(slots=True)
class SessionDetailView:
    """Represents the fully prepared data needed by the detail pane."""

    session_id: str
    display_title: str
    messages: list[DisplayMessage] = field(default_factory=list)
    warnings: list[DisplayWarning] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate the required fields."""
        if not self.session_id:
            msg = 'session_id must not be empty'
            raise ValueError(msg)
        if not self.display_title:
            msg = 'display_title must not be empty'
            raise ValueError(msg)


@dataclass(slots=True)
class MarkdownDocument:
    """Represents one generated Markdown document."""

    session_id: str
    title: str
    body: str
    suggested_filename: str

    def __post_init__(self) -> None:
        """Validate the required fields."""
        if not self.session_id:
            msg = 'session_id must not be empty'
            raise ValueError(msg)
        if not self.title:
            msg = 'title must not be empty'
            raise ValueError(msg)
        if not self.suggested_filename:
            msg = 'suggested_filename must not be empty'
            raise ValueError(msg)


@dataclass(slots=True)
class ExportBatch:
    """Represents one batch export request."""

    session_ids: list[str]
    output_directory: Path

    def __post_init__(self) -> None:
        """Validate the required fields."""
        if not self.session_ids:
            msg = 'session_ids must not be empty'
            raise ValueError(msg)


__all__ = [
    'DisplayMessage',
    'DisplayWarning',
    'ExportBatch',
    'IssueSeverity',
    'JsonObject',
    'LegacySessionSource',
    'MarkdownDocument',
    'Message',
    'MessageFormat',
    'MessageRole',
    'ParseIssue',
    'Session',
    'SessionDetailView',
    'SessionListItem',
    'SessionMetadata',
    'SessionMetadataSource',
    'SessionSourceKind',
    'TranscriptEvent',
    'TranscriptFile',
]
