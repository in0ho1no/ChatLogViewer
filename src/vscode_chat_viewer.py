"""VS Code chat log viewer built with the Python standard library."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname


APP_TITLE = 'VS Code Chat Log Viewer'
DEFAULT_PREVIEW_LENGTH = 20
IGNORED_RESPONSE_KINDS = {
    'mcpServersStarting',
    'progressTaskSerialized',
    'thinking',
    'toolInvocationSerialized',
}


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
        """Return the updated date formatted for the list view."""
        if self.updated_at_ms is None:
            return ''
        return format_timestamp(self.updated_at_ms, '%Y/%m/%d')


def format_timestamp(timestamp_ms: int, pattern: str) -> str:
    """Format a millisecond unix timestamp as local time."""
    return datetime.fromtimestamp(timestamp_ms / 1000).strftime(pattern)


def extract_text(value: Any) -> str:
    """Extract a plain text string from mixed JSON structures."""
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if isinstance(value.get('text'), str):
            return value['text']
        parts = value.get('parts')
        if isinstance(parts, list):
            fragments = [extract_text(part) for part in parts]
            return ''.join(fragment for fragment in fragments if fragment)
        if isinstance(value.get('value'), str):
            return value['value']
    if isinstance(value, list):
        return ''.join(fragment for fragment in (extract_text(item) for item in value) if fragment)
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

    for key in ('folder', 'workspace', 'configuration'):
        value = payload.get(key)
        if isinstance(value, str):
            decoded = decode_file_uri(value)
            return decoded or str(workspace_storage_dir)
    return str(workspace_storage_dir)


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
    value = item.get('value')
    if isinstance(value, str):
        return value
    return ''


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

        assistant_chunks: list[str] = []
        for item in request.get('response', []):
            if not isinstance(item, dict):
                continue
            visible_text = extract_visible_response_text(item)
            if visible_text:
                append_assistant_chunk(assistant_chunks, visible_text)
        flush_assistant_chunks(messages, assistant_chunks, timestamp_ms)

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
        f'# {session.display_title}',
        '',
        f'- Session ID: `{session.session_id}`',
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

    lines.extend(['', '---', ''])

    if not session.messages:
        lines.append('_No chat messages could be reconstructed from this session._')
    else:
        for index, message in enumerate(session.messages, start=1):
            role_label = 'User' if message.role == 'user' else 'Assistant'
            lines.append(f'## {index}. {role_label}')
            lines.append('')
            lines.append(message.text.rstrip())
            lines.append('')

    if session.parse_errors:
        lines.extend(['---', '', '## Parse Warnings', ''])
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
        toolbar.columnconfigure(3, weight=1)

        ttk.Label(toolbar, text=APP_TITLE, font=('Yu Gothic UI', 12, 'bold')).grid(row=0, column=0, sticky='w')
        ttk.Button(toolbar, text='再スキャン', command=self.refresh_sessions).grid(row=0, column=1, padx=(12, 0))
        ttk.Button(toolbar, text='Markdown保存', command=self.export_selected_session).grid(row=0, column=2, padx=(8, 0))
        ttk.Label(toolbar, textvariable=self.status_var, anchor='e').grid(row=0, column=3, sticky='e')

        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.grid(row=1, column=0, sticky='nsew', padx=10, pady=(0, 10))

        left = ttk.Frame(paned, padding=(0, 0, 8, 0))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            left,
            columns=('message_count', 'updated_at', 'preview'),
            show='headings',
            selectmode='browse',
        )
        self.tree.heading('message_count', text='メッセージ数')
        self.tree.heading('updated_at', text='最終更新日時')
        self.tree.heading('preview', text='先頭メッセージ')
        self.tree.column('message_count', width=110, anchor='center', stretch=False)
        self.tree.column('updated_at', width=120, anchor='center', stretch=False)
        self.tree.column('preview', width=320, anchor='w', stretch=True)
        self.tree.grid(row=0, column=0, sticky='nsew')
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)

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
        self.session_by_item_id.clear()
        self.tree.delete(*self.tree.get_children())

        for index, session in enumerate(sessions):
            item_id = str(index)
            preview = shorten_text(session.preview_text, DEFAULT_PREVIEW_LENGTH)
            self.tree.insert(
                '',
                'end',
                iid=item_id,
                values=(session.message_count, session.updated_at_label, preview),
            )
            self.session_by_item_id[item_id] = session

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
        selection = self.tree.selection()
        if not selection:
            return
        session = self.session_by_item_id.get(selection[0])
        if session is not None:
            self.show_session(session)

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

    def get_selected_session(self) -> ChatSession | None:
        """Return the currently selected session."""
        selection = self.tree.selection()
        if not selection:
            return None
        return self.session_by_item_id.get(selection[0])

    def export_selected_session(self) -> None:
        """Export the selected session to a Markdown file."""
        session = self.get_selected_session()
        if session is None:
            messagebox.showinfo(APP_TITLE, '先に履歴を選択してください。')
            return

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

    def open_selected_folder(self) -> None:
        """Open the folder that contains the selected source file."""
        session = self.get_selected_session()
        if session is None:
            messagebox.showinfo(APP_TITLE, '先に履歴を選択してください。')
            return
        folder = session.folder_path
        if not folder.exists():
            messagebox.showerror(APP_TITLE, f'フォルダが見つかりません。\n\n{folder}')
            return

        os.startfile(folder)  # type: ignore[attr-defined]


def shorten_text(text: str, limit: int) -> str:
    """Shorten text for list display without breaking empty values."""
    compact = ' '.join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + '...'


def sanitize_filename(value: str) -> str:
    """Sanitize a string for use as a Windows filename."""
    invalid_chars = '<>:"/\\|?*'
    sanitized = ''.join('_' if char in invalid_chars else char for char in value).strip()
    sanitized = sanitized.rstrip('. ')
    return sanitized[:120]


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
    'build_markdown',
    'decode_file_uri',
    'discover_chat_sessions',
    'extract_text',
    'launch_app',
    'load_workspace_label',
    'parse_chat_session',
    'sanitize_filename',
    'shorten_text',
]
