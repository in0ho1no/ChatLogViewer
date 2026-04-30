"""VS Code chat log viewer built with the Python standard library."""

from __future__ import annotations

import json
import os
import re
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

APP_TITLE = 'VS Code Chat Log Viewer'
DEFAULT_PREVIEW_LENGTH = 20
SORTABLE_COLUMNS = ('message_count', 'updated_at', 'preview')
IGNORED_RESPONSE_KINDS = {
    'mcpServersStarting',
    'progressTaskSerialized',
    'thinking',
    'toolInvocationSerialized',
}

# Copilot Chat logs can produce deeply nested message structures during history
# restoration. 128 levels gives generous room above any real-world nesting
# while still guarding against pathological inputs.
_EXTRACT_TEXT_MAX_DEPTH = 128


@dataclass(slots=True)
class ChatMessage:
    """A normalized chat message."""

    role: str
    text: str
    timestamp_ms: int | None = None


@dataclass(slots=True)
class ChatSession:
    """A normalized VS Code chat session."""

    session_id: str
    session_path: Path
    workspace_path: str
    workspace_storage_path: Path
    created_at_ms: int | None
    updated_at_ms: int | None
    preview_text: str
    custom_title: str | None
    responder_username: str | None
    model_id: str | None
    messages: list[ChatMessage] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)

    @property
    def message_count(self) -> int:
        """Return the number of normalized messages."""
        return len(self.messages)

    @property
    def folder_path(self) -> Path:
        """Return the folder that contains the source JSONL file."""
        return self.session_path.parent

    @property
    def display_title(self) -> str:
        """Return a friendly title for the session."""
        if self.custom_title:
            return self.custom_title
        if self.preview_text:
            return self.preview_text
        return self.session_id

    @property
    def updated_at_label(self) -> str:
        """Return the updated timestamp formatted for the list view."""
        if self.updated_at_ms is None:
            return ''
        return format_timestamp(self.updated_at_ms, '%Y/%m/%d %H:%M')


def format_timestamp(timestamp_ms: int, pattern: str) -> str:
    """Format a millisecond unix timestamp as local time."""
    return datetime.fromtimestamp(timestamp_ms / 1000).strftime(pattern)


def extract_text(value: Any, _depth: int = 0) -> str:
    """Extract a plain text string from mixed JSON structures."""
    if _depth > _EXTRACT_TEXT_MAX_DEPTH:
        return ''
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        text_val = value.get('text')
        if isinstance(text_val, str):
            return text_val
        parts = value.get('parts')
        if isinstance(parts, list):
            fragments = [extract_text(part, _depth + 1) for part in parts]
            return ''.join(fragment for fragment in fragments if fragment)
        value_val = value.get('value')
        if isinstance(value_val, str):
            return value_val
    if isinstance(value, list):
        return ''.join(fragment for fragment in (extract_text(item, _depth + 1) for item in value) if fragment)
    return ''


def decode_file_uri(uri: str) -> str:
    """Decode a VS Code file URI into a Windows path string."""
    if not uri:
        return ''
    parsed = urlparse(uri)
    if parsed.scheme != 'file':
        return uri

    path = url2pathname(unquote(parsed.path))
    if parsed.netloc:
        return f'\\\\{parsed.netloc}{path}'
    if len(path) >= 3 and path[0] == '/' and path[2] == ':':
        return path[1:]
    return path


def load_workspace_label(workspace_storage_dir: Path) -> str:
    """Load a friendly workspace label from workspace.json when available."""
    workspace_file = workspace_storage_dir / 'workspace.json'
    if not workspace_file.exists():
        return str(workspace_storage_dir)

    try:
        payload = json.loads(workspace_file.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return str(workspace_storage_dir)

    if not isinstance(payload, dict):
        return str(workspace_storage_dir)

    for key in ('folder', 'workspace', 'configuration'):
        value = payload.get(key)
        if isinstance(value, str):
            decoded = decode_file_uri(value)
            return decoded or str(workspace_storage_dir)
    return str(workspace_storage_dir)


def extract_windows_username(path: Path) -> str | None:
    r"""Extract the Windows username from a path under C:\Users\<name>."""
    parts = path.parts
    for index, part in enumerate(parts[:-1]):
        if part.casefold() == 'users' and index + 1 < len(parts):
            return parts[index + 1]
    return None


# Only these file extensions are safe to open with os.startfile().
# Directories are always allowed; .code-workspace opens VS Code itself.
_SAFE_OPEN_SUFFIXES = frozenset({'.code-workspace'})


def resolve_workspace_open_path(workspace_path: str) -> Path | None:
    """Resolve a workspace label into a path that can be opened in Explorer.

    Returns a directory or a .code-workspace file; rejects any other file type
    to prevent os.startfile() from inadvertently executing arbitrary files.
    """
    if not workspace_path:
        return None
    candidate = Path(workspace_path)
    if candidate.is_dir():
        return candidate
    if candidate.is_file() and candidate.suffix.lower() in _SAFE_OPEN_SUFFIXES:
        return candidate
    return None


def append_assistant_chunk(chunks: list[str], text: str) -> None:
    """Append a visible assistant chunk while avoiding exact duplicates."""
    normalized = text.strip()
    if not normalized:
        return
    if chunks and chunks[-1] == normalized:
        return
    chunks.append(normalized)


def flush_assistant_chunks(messages: list[ChatMessage], chunks: list[str], timestamp_ms: int | None) -> None:
    """Flush buffered assistant chunks into one message."""
    if not chunks:
        return
    messages.append(ChatMessage(role='assistant', text='\n\n'.join(chunks), timestamp_ms=timestamp_ms))
    chunks.clear()


def extract_visible_response_text(item: dict[str, Any]) -> str:
    """Extract a visible assistant text fragment from a response item."""
    kind = item.get('kind')
    if kind in IGNORED_RESPONSE_KINDS:
        return ''
    if kind == 'inlineReference':
        name = item.get('name')
        if isinstance(name, str) and name:
            return f'`{name}`'
        return ''
    value = item.get('value')
    if isinstance(value, str):
        return value
    return ''


def merge_response_fragments(existing: str, fragment: str) -> str:
    """Merge one visible response fragment into an accumulated run."""
    if not existing:
        return fragment
    if fragment.startswith(existing):
        return fragment
    if existing.endswith(fragment):
        return existing

    max_overlap = min(len(existing), len(fragment))
    for overlap in range(max_overlap, 0, -1):
        if existing.endswith(fragment[:overlap]):
            return existing + fragment[overlap:]

    if should_insert_paragraph_break(existing, fragment):
        return existing + '\n\n' + fragment
    return existing + fragment


def should_insert_paragraph_break(existing: str, fragment: str) -> bool:
    """Decide whether two non-overlapping fragments should form separate paragraphs."""
    if not existing or not fragment:
        return False
    if fragment.startswith((' ', '\n', '\t', '`', '、', '。', ',', '.', ':', ';', ')', ']', '}')):
        return False
    if existing.endswith((' ', '\n', '\t', '`', '、', ',', ':', ';', '(', '[', '{')):
        return False
    return existing.endswith(('。', '！', '？', '!', '?'))


def build_assistant_response_text(response_items: list[dict[str, Any]]) -> str:
    """Reconstruct one assistant message from streamed response items."""
    runs: list[str] = []
    current_run = ''

    for item in response_items:
        if not isinstance(item, dict):
            continue
        fragment = extract_visible_response_text(item)
        if fragment:
            current_run = merge_response_fragments(current_run, fragment)
            continue
        if current_run.strip():
            append_assistant_chunk(runs, current_run)
        current_run = ''

    if current_run.strip():
        append_assistant_chunk(runs, current_run)
    return '\n\n'.join(runs)


def extract_tool_round_responses(result: Any) -> list[str]:
    """Extract cleaner progress responses from request result metadata when present."""
    if not isinstance(result, dict):
        return []
    metadata = result.get('metadata')
    if not isinstance(metadata, dict):
        return []
    rounds = metadata.get('toolCallRounds')
    if not isinstance(rounds, list):
        return []

    responses: list[str] = []
    for round_item in rounds:
        if not isinstance(round_item, dict):
            continue
        response = round_item.get('response')
        if not isinstance(response, str):
            continue
        normalized = response.strip()
        if not normalized:
            continue
        append_assistant_chunk(responses, normalized)
    return responses


def normalize_response_text_for_comparison(text: str) -> str:
    """Normalize response text for loose duplicate detection."""
    normalized = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'`\1`', text)
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized.strip()


def extract_final_response_text(response_items: list[dict[str, Any]]) -> str:
    """Extract the final assistant answer from visible response items."""
    last_thinking_index = -1
    for index, item in enumerate(response_items):
        if item.get('kind') == 'thinking':
            last_thinking_index = index

    tail_items = response_items[last_thinking_index + 1 :] if last_thinking_index >= 0 else response_items
    tail_text = build_assistant_response_text(tail_items)
    if tail_text:
        return tail_text
    return build_assistant_response_text(response_items)


def build_assistant_message_text(request: dict[str, Any]) -> str:
    """Build one assistant message, preferring cleaner stored progress metadata when available."""
    response_items = [item for item in request.get('response', []) if isinstance(item, dict)]
    progress_responses = extract_tool_round_responses(request.get('result'))
    final_response = extract_final_response_text(response_items)

    chunks: list[str] = []
    for chunk in progress_responses:
        append_assistant_chunk(chunks, chunk)
    if final_response and not is_effectively_duplicate_chunk(chunks, final_response):
        append_assistant_chunk(chunks, final_response)
    if chunks:
        return '\n\n'.join(chunks)
    return build_assistant_response_text(response_items)


def is_effectively_duplicate_chunk(existing_chunks: list[str], candidate: str) -> bool:
    """Return whether the candidate is already present in the existing chunks."""
    normalized_candidate = normalize_response_text_for_comparison(candidate)
    if not normalized_candidate:
        return True
    for chunk in reversed(existing_chunks):
        normalized_chunk = normalize_response_text_for_comparison(chunk)
        if normalized_chunk == normalized_candidate:
            return True
        if normalized_candidate in normalized_chunk:
            return True
    return False


def parse_chat_session(session_path: Path, workspace_path: str, workspace_storage_dir: Path) -> ChatSession:
    """Parse one VS Code chat session JSONL file into a normalized model."""
    metadata: dict[str, Any] = {}
    requests: list[dict[str, Any]] = []
    current_input_text = ''
    custom_title: str | None = None
    parse_errors: list[str] = []

    try:
        with session_path.open('r', encoding='utf-8') as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                if not raw_line.strip():
                    continue
                try:
                    payload = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    parse_errors.append(f'Line {line_number}: {exc.msg}')
                    continue

                kind = payload.get('kind')
                key_path = payload.get('k', [])

                if kind == 0:
                    metadata = payload.get('v', {})
                    if not custom_title and isinstance(metadata.get('customTitle'), str):
                        custom_title = metadata['customTitle']
                    continue

                if kind == 1:
                    if key_path == ['inputState', 'inputText']:
                        current_input_text = extract_text(payload.get('v'))
                    elif key_path == ['customTitle']:
                        title_text = extract_text(payload.get('v')).strip()
                        if title_text:
                            custom_title = title_text
                    elif len(key_path) == 3 and key_path[0] == 'requests' and key_path[2] == 'result':
                        request_index = key_path[1]
                        if isinstance(request_index, int) and 0 <= request_index < len(requests):
                            requests[request_index]['result'] = payload.get('v')
                    continue

                if kind != 2:
                    continue

                if key_path == ['requests']:
                    for request in payload.get('v', []):
                        request_copy = dict(request)
                        request_copy.setdefault('response', [])
                        request_copy['_input_text'] = current_input_text
                        requests.append(request_copy)
                    continue

                if len(key_path) == 3 and key_path[0] == 'requests' and key_path[2] == 'response':
                    request_index = key_path[1]
                    if isinstance(request_index, int) and 0 <= request_index < len(requests):
                        response_items = requests[request_index].setdefault('response', [])
                        if isinstance(response_items, list):
                            response_items.extend(payload.get('v', []))

    except OSError as exc:
        parse_errors.append(str(exc))

    messages: list[ChatMessage] = []
    preview_text = ''
    updated_at_ms = metadata.get('creationDate')
    model_id = None

    for request in requests:
        timestamp_ms = request.get('timestamp')
        if isinstance(timestamp_ms, int):
            updated_at_ms = max(updated_at_ms or timestamp_ms, timestamp_ms)

        user_text = extract_text(request.get('message')) or extract_text(request.get('_input_text'))
        user_text = user_text.strip()
        if user_text:
            messages.append(ChatMessage(role='user', text=user_text, timestamp_ms=timestamp_ms))
            if not preview_text:
                preview_text = user_text

        if model_id is None:
            model_candidate = request.get('modelId')
            if isinstance(model_candidate, str):
                model_id = model_candidate

        assistant_text = build_assistant_message_text(request)
        if assistant_text:
            messages.append(ChatMessage(role='assistant', text=assistant_text, timestamp_ms=timestamp_ms))

    return ChatSession(
        session_id=str(metadata.get('sessionId') or session_path.stem),
        session_path=session_path,
        workspace_path=workspace_path,
        workspace_storage_path=workspace_storage_dir,
        created_at_ms=metadata.get('creationDate'),
        updated_at_ms=updated_at_ms,
        preview_text=preview_text,
        custom_title=custom_title,
        responder_username=metadata.get('responderUsername'),
        model_id=model_id,
        messages=messages,
        parse_errors=parse_errors,
    )


def build_markdown(session: ChatSession) -> str:
    """Build a Markdown document from a normalized session."""
    lines = [
        '# Chat Session',
        '',
        session.display_title,
        '',
        '## Metadata',
        '',
        f'- Session ID: `{session.session_id}`',
        f'- User: `{extract_windows_username(session.session_path) or "Unknown"}`',
        f'- Workspace: `{session.workspace_path}`',
        f'- Source File: `{session.session_path}`',
    ]

    if session.created_at_ms is not None:
        lines.append(f'- Created: {format_timestamp(session.created_at_ms, "%Y/%m/%d %H:%M:%S")}')
    if session.updated_at_ms is not None:
        lines.append(f'- Updated: {format_timestamp(session.updated_at_ms, "%Y/%m/%d %H:%M:%S")}')
    if session.model_id:
        lines.append(f'- Model: `{session.model_id}`')
    if session.parse_errors:
        lines.append(f'- Parse Warnings: {len(session.parse_errors)}')

    lines.extend(['', '# Conversation', ''])

    if not session.messages:
        lines.append('_No chat messages could be reconstructed from this session._')
    else:
        for message in session.messages:
            role_label = 'User' if message.role == 'user' else 'Assistant'
            lines.append(f'## {role_label}')
            lines.append('')
            if message.role == 'user' and message.timestamp_ms is not None:
                lines.append(format_timestamp(message.timestamp_ms, '%Y/%m/%d %H:%M'))
                lines.append('')
            lines.append(message.text.rstrip())
            lines.append('')

    if session.parse_errors:
        lines.extend(['# Parse Warnings', ''])
        for warning in session.parse_errors:
            lines.append(f'- {warning}')

    return '\n'.join(lines).rstrip() + '\n'


def discover_chat_sessions(user_root: Path | None = None) -> list[ChatSession]:
    """Discover and parse chat sessions under the VS Code user storage."""
    vscode_user_dir = user_root or Path(os.environ.get('APPDATA', '')) / 'Code' / 'User'
    workspace_storage_root = vscode_user_dir / 'workspaceStorage'
    if not workspace_storage_root.exists():
        return []

    sessions: list[ChatSession] = []
    for workspace_dir in sorted(path for path in workspace_storage_root.iterdir() if path.is_dir()):
        workspace_path = load_workspace_label(workspace_dir)
        chat_dir = workspace_dir / 'chatSessions'
        if not chat_dir.exists():
            continue
        for session_path in sorted(chat_dir.glob('*.jsonl')):
            session = parse_chat_session(session_path, workspace_path, workspace_dir)
            if session.message_count == 0 and not session.custom_title:
                continue
            sessions.append(session)

    sessions.sort(key=lambda session: session.updated_at_ms or 0, reverse=True)
    return sessions


class ChatLogViewerApp:
    """Tkinter desktop app for browsing VS Code chat logs."""

    def __init__(self, root: tk.Tk) -> None:
        """Initialize the application."""
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry('1280x820')
        self.root.minsize(980, 640)

        self.sessions: list[ChatSession] = []
        self.session_by_item_id: dict[str, ChatSession] = {}
        self.sort_column = 'updated_at'
        self.sort_desc = True

        self.status_var = tk.StringVar(value='Ready')
        self.source_path_var = tk.StringVar(value='')
        self.workspace_var = tk.StringVar(value='')

        self._build_ui()
        self.root.after(50, self.refresh_sessions)

    def _build_ui(self) -> None:
        """Build the Tkinter widget tree."""
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self.root, padding=(10, 10, 10, 6))
        toolbar.grid(row=0, column=0, sticky='ew')
        toolbar.columnconfigure(4, weight=1)

        ttk.Label(toolbar, text=APP_TITLE, font=('Yu Gothic UI', 12, 'bold')).grid(row=0, column=0, sticky='w')
        ttk.Button(toolbar, text='再スキャン', command=self.refresh_sessions).grid(row=0, column=1, padx=(12, 0))
        ttk.Button(toolbar, text='Markdown保存', command=self.export_selected_sessions).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(toolbar, text='Markdown一括保存', command=self.export_selected_sessions_to_directory).grid(row=0, column=3, padx=(8, 0))
        ttk.Label(toolbar, textvariable=self.status_var, anchor='e').grid(row=0, column=4, sticky='e')

        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.grid(row=1, column=0, sticky='nsew', padx=10, pady=(0, 10))

        left = ttk.Frame(paned, padding=(0, 0, 8, 0))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            left,
            columns=('message_count', 'updated_at', 'preview'),
            show='headings',
            selectmode='extended',
        )
        self.tree.heading('message_count', command=lambda: self.on_sort_column('message_count'))
        self.tree.heading('updated_at', command=lambda: self.on_sort_column('updated_at'))
        self.tree.heading('preview', command=lambda: self.on_sort_column('preview'))
        self.tree.column('message_count', width=110, anchor='center', stretch=False)
        self.tree.column('updated_at', width=120, anchor='center', stretch=False)
        self.tree.column('preview', width=320, anchor='w', stretch=True)
        self.tree.grid(row=0, column=0, sticky='nsew')
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        self._update_tree_headings()

        tree_scroll = ttk.Scrollbar(left, orient='vertical', command=self.tree.yview)
        tree_scroll.grid(row=0, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=tree_scroll.set)

        right = ttk.Frame(paned)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        info = ttk.Frame(right, padding=(0, 0, 0, 8))
        info.grid(row=0, column=0, sticky='ew')
        info.columnconfigure(1, weight=1)

        ttk.Label(info, text='保存ファイル:', width=10).grid(row=0, column=0, sticky='nw')
        ttk.Label(info, textvariable=self.source_path_var, justify='left').grid(row=0, column=1, sticky='ew')
        ttk.Button(info, text='保存フォルダを開く', command=self.open_selected_folder).grid(row=0, column=2, padx=(8, 0))

        ttk.Label(info, text='ワークスペース:', width=10).grid(row=1, column=0, sticky='nw', pady=(6, 0))
        ttk.Label(info, textvariable=self.workspace_var, justify='left').grid(row=1, column=1, sticky='ew', pady=(6, 0))
        ttk.Button(info, text='Workspaceを開く', command=self.open_selected_workspace).grid(row=1, column=2, padx=(8, 0), pady=(6, 0))

        text_frame = ttk.Frame(right)
        text_frame.grid(row=1, column=0, sticky='nsew')
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.text = tk.Text(
            text_frame,
            wrap='word',
            state='disabled',
            font=('Yu Gothic UI', 10),
            padx=14,
            pady=14,
        )
        self.text.grid(row=0, column=0, sticky='nsew')

        text_scroll = ttk.Scrollbar(text_frame, orient='vertical', command=self.text.yview)
        text_scroll.grid(row=0, column=1, sticky='ns')
        self.text.configure(yscrollcommand=text_scroll.set)

        self._configure_text_tags()

        paned.add(left, weight=1)
        paned.add(right, weight=3)

    def _configure_text_tags(self) -> None:
        """Configure tags used for lightweight Markdown styling."""
        self.text.tag_configure('heading1', font=('Yu Gothic UI', 16, 'bold'), spacing1=10, spacing3=6)
        self.text.tag_configure('heading2', font=('Yu Gothic UI', 13, 'bold'), spacing1=8, spacing3=4)
        self.text.tag_configure('bullet', lmargin1=16, lmargin2=32)
        self.text.tag_configure('code', font=('Consolas', 10), background='#f2f2f2')
        self.text.tag_configure('muted', foreground='#666666')

    def refresh_sessions(self) -> None:
        """Scan the VS Code storage and refresh the list view."""
        self.status_var.set('スキャン中...')
        self.root.update_idletasks()

        try:
            sessions = discover_chat_sessions()
        except Exception as exc:  # pragma: no cover - defensive UI handling
            messagebox.showerror(APP_TITLE, f'スキャンに失敗しました。\n\n{exc}')
            self.status_var.set('スキャン失敗')
            return

        self.sessions = sessions
        self._sort_sessions()
        self._populate_tree()

        if sessions:
            first_item_id = self.tree.get_children()[0]
            self.tree.selection_set(first_item_id)
            self.tree.focus(first_item_id)
            self.show_session(self.session_by_item_id[first_item_id])
            self.status_var.set(f'{len(sessions)} 件の履歴を読み込みました')
        else:
            self.show_placeholder('VS Code のチャット履歴は見つかりませんでした。')
            self.status_var.set('履歴が見つかりません')

    def on_tree_select(self, _event: tk.Event[tk.Misc]) -> None:
        """Display the selected session."""
        sessions = self.get_selected_sessions()
        if not sessions:
            return
        focus_item = self.tree.focus()
        session = self.session_by_item_id.get(focus_item) or sessions[0]
        self.show_session(session)
        self.status_var.set(f'{len(sessions)} 件を選択中')

    def show_session(self, session: ChatSession) -> None:
        """Show a session in the right-hand Markdown panel."""
        self.source_path_var.set(str(session.session_path))
        self.workspace_var.set(session.workspace_path)
        self.render_markdown(build_markdown(session))

    def show_placeholder(self, text: str) -> None:
        """Show placeholder text when there is no session to display."""
        self.source_path_var.set('')
        self.workspace_var.set('')
        self.render_markdown(text)

    def render_markdown(self, markdown_text: str) -> None:
        """Render Markdown text with lightweight Text widget styling."""
        self.text.configure(state='normal')
        self.text.delete('1.0', 'end')

        in_code_block = False
        for raw_line in markdown_text.splitlines():
            line = raw_line.rstrip('\n')
            tag = None

            if line.startswith('```'):
                in_code_block = not in_code_block
                self.text.insert('end', line + '\n', ('code',))
                continue

            if in_code_block:
                tag = 'code'
            elif line.startswith('# '):
                tag = 'heading1'
            elif line.startswith('## '):
                tag = 'heading2'
            elif line.startswith('- '):
                tag = 'bullet'
            elif line.startswith('_') and line.endswith('_'):
                tag = 'muted'

            if tag:
                self.text.insert('end', line + '\n', (tag,))
            else:
                self.text.insert('end', line + '\n')

        self.text.configure(state='disabled')
        self.text.yview_moveto(0.0)

    def get_selected_sessions(self) -> list[ChatSession]:
        """Return the currently selected sessions in tree order."""
        selected_ids = set(self.tree.selection())
        sessions: list[ChatSession] = []
        for item_id in self.tree.get_children():
            if item_id in selected_ids:
                session = self.session_by_item_id.get(item_id)
                if session is not None:
                    sessions.append(session)
        return sessions

    def export_selected_sessions(self) -> None:
        """Export one selected session or many selected sessions."""
        sessions = self.get_selected_sessions()
        if not sessions:
            messagebox.showinfo(APP_TITLE, '先に履歴を選択してください。')
            return
        if len(sessions) == 1:
            self._export_single_session(sessions[0])
            return
        self._export_multiple_sessions(sessions)

    def export_selected_sessions_to_directory(self) -> None:
        """Export the selected sessions into a chosen directory."""
        sessions = self.get_selected_sessions()
        if not sessions:
            messagebox.showinfo(APP_TITLE, '先に履歴を選択してください。')
            return
        self._export_multiple_sessions(sessions)

    def _export_single_session(self, session: ChatSession) -> None:
        """Export one session to a Markdown file."""
        default_name = sanitize_filename(session.display_title) or session.session_id
        default_path = session.folder_path / f'{default_name}.md'
        target = filedialog.asksaveasfilename(
            title='Markdown保存',
            defaultextension='.md',
            initialfile=default_path.name,
            initialdir=str(default_path.parent),
            filetypes=[('Markdown', '*.md'), ('All Files', '*.*')],
        )
        if not target:
            return

        output_path = Path(target)
        output_path.write_text(build_markdown(session), encoding='utf-8')
        self.status_var.set(f'Markdown を保存しました: {output_path}')

    def _export_multiple_sessions(self, sessions: list[ChatSession]) -> None:
        """Export multiple sessions into a chosen directory."""
        target_dir = filedialog.askdirectory(title='Markdown保存先フォルダ')
        if not target_dir:
            return

        output_dir = Path(target_dir)
        saved_paths: list[Path] = []
        failures: list[str] = []
        used_names: set[str] = set()

        for session in sessions:
            base_name = sanitize_filename(session.display_title) or session.session_id
            filename = make_unique_filename(base_name, used_names)
            output_path = output_dir / filename
            try:
                output_path.write_text(build_markdown(session), encoding='utf-8')
            except OSError as exc:
                failures.append(f'{session.display_title}: {exc}')
                continue
            used_names.add(filename.casefold())
            saved_paths.append(output_path)

        if failures:
            messagebox.showerror(
                APP_TITLE,
                f'{len(saved_paths)} 件保存、{len(failures)} 件失敗しました。\n\n' + '\n'.join(failures[:10]),
            )
        else:
            messagebox.showinfo(APP_TITLE, f'{len(saved_paths)} 件の Markdown を保存しました。')

        if saved_paths:
            self.status_var.set(f'{len(saved_paths)} 件の Markdown を保存しました: {output_dir}')

    def on_sort_column(self, column_name: str) -> None:
        """Sort the session list by the requested column."""
        if column_name not in SORTABLE_COLUMNS:
            return
        if self.sort_column == column_name:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_column = column_name
            self.sort_desc = column_name in {'message_count', 'updated_at'}
        self._sort_sessions()
        self._populate_tree(preserve_selection=True)
        self._update_tree_headings()

    def _sort_sessions(self) -> None:
        """Sort the in-memory session list using the current sort state."""

        def sort_key(session: ChatSession) -> tuple[Any, str]:
            if self.sort_column == 'message_count':
                return (session.message_count, str(session.session_path).casefold())
            if self.sort_column == 'updated_at':
                return (session.updated_at_ms or 0, str(session.session_path).casefold())
            return (session.preview_text.casefold(), str(session.session_path).casefold())

        self.sessions.sort(key=sort_key, reverse=self.sort_desc)

    def _populate_tree(self, preserve_selection: bool = False) -> None:
        """Populate the tree widget from the current session list."""
        selected_ids = tuple(item_id for item_id in self.tree.selection() if item_id in self.session_by_item_id)
        focused_id = self.tree.focus()

        self.session_by_item_id.clear()
        self.tree.delete(*self.tree.get_children())

        for session in self.sessions:
            item_id = str(session.session_path)
            preview = shorten_text(session.preview_text, DEFAULT_PREVIEW_LENGTH)
            self.tree.insert(
                '',
                'end',
                iid=item_id,
                values=(session.message_count, session.updated_at_label, preview),
            )
            self.session_by_item_id[item_id] = session

        if preserve_selection:
            restored_ids = [item_id for item_id in selected_ids if item_id in self.session_by_item_id]
            if restored_ids:
                self.tree.selection_set(restored_ids)
                target_focus = focused_id if focused_id in self.session_by_item_id else restored_ids[0]
                self.tree.focus(target_focus)
                self.tree.see(target_focus)

    def _update_tree_headings(self) -> None:
        """Refresh heading labels to reflect the active sort column."""
        labels = {
            'message_count': 'メッセージ数',
            'updated_at': '最終更新日時',
            'preview': '先頭メッセージ',
        }
        for column_name, label in labels.items():
            if self.sort_column == column_name:
                arrow = '▼' if self.sort_desc else '▲'
                label = f'{label} {arrow}'
            self.tree.heading(column_name, text=label)

    def open_selected_folder(self) -> None:
        """Open the folder that contains the selected source file."""
        sessions = self.get_selected_sessions()
        if not sessions:
            messagebox.showinfo(APP_TITLE, '先に履歴を選択してください。')
            return
        session = sessions[0]
        folder = session.folder_path
        if not folder.is_dir():
            messagebox.showerror(APP_TITLE, f'フォルダが見つかりません。\n\n{folder}')
            return

        os.startfile(folder)  # type: ignore[attr-defined]

    def open_selected_workspace(self) -> None:
        """Open the selected workspace path in Explorer."""
        sessions = self.get_selected_sessions()
        if not sessions:
            messagebox.showinfo(APP_TITLE, '先に履歴を選択してください。')
            return

        workspace_path = resolve_workspace_open_path(sessions[0].workspace_path)
        if workspace_path is None:
            messagebox.showerror(APP_TITLE, f'Workspace を開けませんでした。\n\n{sessions[0].workspace_path}')
            return

        os.startfile(workspace_path)  # type: ignore[attr-defined]


def shorten_text(text: str, limit: int) -> str:
    """Shorten text for list display without breaking empty values."""
    compact = ' '.join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + '...'


# Windows reserved device names that cannot be used as filenames.
_WINDOWS_RESERVED_NAMES = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)', re.IGNORECASE)


def sanitize_filename(value: str) -> str:
    """Sanitize a string for use as a Windows filename."""
    # Strip control characters (U+0000–U+001F).
    sanitized = ''.join(char for char in value if ord(char) >= 0x20)
    # Replace characters invalid on Windows.
    invalid_chars = '<>:"/\\|?*'
    sanitized = ''.join('_' if char in invalid_chars else char for char in sanitized).strip()
    sanitized = sanitized.rstrip('. ')
    # Prefix Windows reserved device names to prevent write failures.
    if _WINDOWS_RESERVED_NAMES.match(sanitized):
        sanitized = '_' + sanitized
    return sanitized[:120]


def make_unique_filename(base_name: str, used_names: set[str]) -> str:
    """Return a unique Markdown filename for bulk export."""
    candidate = f'{base_name}.md'
    suffix = 2
    while candidate.casefold() in used_names:
        candidate = f'{base_name} ({suffix}).md'
        suffix += 1
    return candidate


def launch_app() -> None:
    """Launch the Tkinter desktop application."""
    root = tk.Tk()
    ChatLogViewerApp(root)
    root.mainloop()


__all__ = [
    'APP_TITLE',
    'ChatLogViewerApp',
    'ChatMessage',
    'ChatSession',
    'build_assistant_message_text',
    'build_markdown',
    'decode_file_uri',
    'discover_chat_sessions',
    'extract_text',
    'extract_windows_username',
    'launch_app',
    'load_workspace_label',
    'make_unique_filename',
    'parse_chat_session',
    'resolve_workspace_open_path',
    'sanitize_filename',
    'shorten_text',
]
