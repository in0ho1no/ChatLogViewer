"""Tkinter UI for the chat log viewer prototype."""

from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from markdown_export import build_markdown_document
from models import Message, MessageRole, Session, SessionListItem
from scanner import collect_scan_issues, scan_sessions, summarize_scan
from session_list import build_session_list_items

SORT_BY_OPTIONS: tuple[tuple[str, str], ...] = (
    ('タイトル', 'title'),
    ('メッセージ数', 'message_count'),
    ('最終更新', 'latest'),
    ('開始時刻', 'oldest'),
    ('Warnings', 'warnings'),
)

SORT_ORDER_OPTIONS: tuple[tuple[str, str], ...] = (
    ('降順', 'desc'),
    ('昇順', 'asc'),
)

SORT_BY_LABEL_TO_KEY = dict(SORT_BY_OPTIONS)
SORT_ORDER_LABEL_TO_KEY = dict(SORT_ORDER_OPTIONS)
TOKYO_TIMEZONE = timezone(timedelta(hours=9), name='JST')


def format_latest_timestamp(value: object) -> str:
    """Format the latest timestamp for the session list."""
    if value is None:
        return 'n/a'
    if isinstance(value, datetime):
        localized = value.astimezone(TOKYO_TIMEZONE) if value.tzinfo is not None else value
        return localized.strftime('%Y/%m/%d %H:%M:%S')
    return str(value)


def format_warning_flag(has_warnings: bool) -> str:
    """Format the warning state for the session list."""
    return 'yes' if has_warnings else 'no'


def format_message_timestamp(value: object) -> str:
    """Format a message timestamp for the detail pane."""
    if value is None:
        return 'n/a'
    iso_value = getattr(value, 'isoformat', None)
    if callable(iso_value):
        return str(iso_value(timespec='seconds'))
    return str(value)


def build_message_heading(message: Message) -> str:
    """Build the per-message heading shown in the detail pane."""
    role_label = 'USER' if message.role is MessageRole.USER else 'AI'
    timestamp = format_message_timestamp(message.timestamp)
    return f'[{role_label}] {timestamp}'


def resolve_sort_by(value: str) -> str:
    """Resolve the selected sort-by label into its internal key."""
    return SORT_BY_LABEL_TO_KEY.get(value, value)


def resolve_sort_order(value: str) -> str:
    """Resolve the selected sort-order label into its internal key."""
    return SORT_ORDER_LABEL_TO_KEY.get(value, value)


def sort_session_list_items(
    items: list[SessionListItem],
    sort_by: str,
    sort_order: str,
) -> list[SessionListItem]:
    """Sort session list items by the selected timestamp field and order."""
    reverse = sort_order == 'desc'

    def sort_key(item: SessionListItem) -> tuple[object, ...]:
        if sort_by == 'title':
            return (item.display_title.casefold(), item.session_id)
        if sort_by == 'message_count':
            return (item.message_count, item.display_title.casefold(), item.session_id)
        if sort_by == 'warnings':
            return (item.has_warnings, item.display_title.casefold(), item.session_id)
        timestamp = item.latest_timestamp if sort_by == 'latest' else item.oldest_timestamp

        fallback = datetime.min if reverse else datetime.max
        normalized = timestamp if isinstance(timestamp, datetime) else fallback
        missing = timestamp is None
        return (missing, normalized, item.display_title.casefold(), item.session_id)

    return sorted(items, key=sort_key, reverse=reverse)


class ChatLogViewerApp:
    """Minimal Tkinter application shell for browsing scanned sessions."""

    def __init__(self, root: tk.Tk) -> None:
        """Initialize the UI widgets."""
        self.root = root
        self.root.title('Chat Log Viewer')
        self.root.geometry('1200x720')

        self._sessions_by_id: dict[str, Session] = {}
        self._session_list_items: list[SessionListItem] = []
        self._tree_item_to_session: dict[str, tuple[str, str, int, str, bool]] = {}

        self.status_var = tk.StringVar(value='Ready')
        self.detail_var = tk.StringVar(value='No session selected.')
        self.sort_by_var = tk.StringVar(value='最終更新')
        self.sort_order_var = tk.StringVar(value='降順')
        self._selected_session_id: str | None = None

        self._build_layout()

    def load_sessions(self, root_dir: Path) -> None:
        """Scan sessions and populate the left-hand session list."""
        self.status_var.set(f'Scanning sessions under {root_dir}...')
        self.root.update_idletasks()

        sessions = scan_sessions(root_dir)
        self._sessions_by_id = {session.session_id: session for session in sessions}
        self._session_list_items = build_session_list_items(sessions)
        session_count, warning_count = summarize_scan(sessions)
        issues = collect_scan_issues(sessions)

        issue_count = len(issues)
        self.status_var.set(f'Sessions: {session_count}  Warnings: {warning_count}  Issues: {issue_count}  Root: {root_dir}')
        self._refresh_session_tree()

        if self._session_list_items:
            first_item = self.session_tree.get_children()[0]
            self.session_tree.selection_set(first_item)
            self._handle_session_selected(None)
        else:
            self.detail_var.set('No sessions found.')
            self._set_detail_text('No sessions found.')

    def _build_layout(self) -> None:
        """Create the main two-pane layout."""
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        paned = ttk.Panedwindow(container, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(paned, padding=(0, 0, 12, 0))
        right_frame = ttk.Frame(paned)

        paned.add(left_frame, weight=2)
        paned.add(right_frame, weight=3)

        self._build_session_tree(left_frame)
        self._build_detail_panel(right_frame)

        status_label = ttk.Label(container, textvariable=self.status_var, anchor=tk.W)
        status_label.pack(fill=tk.X, pady=(8, 0))

    def _build_session_tree(self, parent: ttk.Frame) -> None:
        """Create the left session list pane."""
        title_label = ttk.Label(parent, text='Sessions')
        title_label.pack(anchor=tk.W, pady=(0, 8))

        controls = ttk.Frame(parent)
        controls.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(controls, text='並び替え').pack(side=tk.LEFT)
        sort_by_box = ttk.Combobox(
            controls,
            textvariable=self.sort_by_var,
            values=tuple(label for label, _ in SORT_BY_OPTIONS),
            state='readonly',
            width=12,
        )
        sort_by_box.pack(side=tk.LEFT, padx=(6, 12))
        sort_by_box.bind('<<ComboboxSelected>>', self._handle_sort_changed)

        ttk.Label(controls, text='順序').pack(side=tk.LEFT)
        sort_order_box = ttk.Combobox(
            controls,
            textvariable=self.sort_order_var,
            values=tuple(label for label, _ in SORT_ORDER_OPTIONS),
            state='readonly',
            width=8,
        )
        sort_order_box.pack(side=tk.LEFT, padx=(6, 0))
        sort_order_box.bind('<<ComboboxSelected>>', self._handle_sort_changed)

        columns = ('messages', 'latest', 'warnings')
        self.session_tree = ttk.Treeview(parent, columns=columns, show='tree headings', selectmode='browse')
        self.session_tree.heading('#0', text='タイトル', command=lambda: self._handle_heading_sort('title'))
        self.session_tree.heading('messages', text='メッセージ数', command=lambda: self._handle_heading_sort('message_count'))
        self.session_tree.heading('latest', text='最終更新', command=lambda: self._handle_heading_sort('latest'))
        self.session_tree.heading('warnings', text='Warnings', command=lambda: self._handle_heading_sort('warnings'))
        self.session_tree.column('#0', width=360, anchor=tk.W)
        self.session_tree.column('messages', width=90, anchor=tk.E)
        self.session_tree.column('latest', width=150, anchor=tk.W)
        self.session_tree.column('warnings', width=80, anchor=tk.CENTER)
        self.session_tree.pack(fill=tk.BOTH, expand=True)
        self.session_tree.bind('<<TreeviewSelect>>', self._handle_session_selected)

    def _refresh_session_tree(self) -> None:
        """Rebuild the session tree using the selected sort settings."""
        selected_session_id: str | None = None
        current_selection = self.session_tree.selection()
        if current_selection:
            selected_session_id = self._tree_item_to_session.get(current_selection[0], ('', '', 0, '', False))[0] or None

        sorted_items = sort_session_list_items(
            self._session_list_items,
            sort_by=resolve_sort_by(self.sort_by_var.get()),
            sort_order=resolve_sort_order(self.sort_order_var.get()),
        )

        self.session_tree.delete(*self.session_tree.get_children())
        self._tree_item_to_session.clear()

        selected_row_id: str | None = None
        for item in sorted_items:
            tree_item_id = self.session_tree.insert(
                '',
                'end',
                text=item.display_title,
                values=(
                    str(item.message_count),
                    format_latest_timestamp(item.latest_timestamp),
                    format_warning_flag(item.has_warnings),
                ),
            )
            self._tree_item_to_session[tree_item_id] = (
                item.session_id,
                item.display_title,
                item.message_count,
                format_latest_timestamp(item.latest_timestamp),
                item.has_warnings,
            )
            if item.session_id == selected_session_id:
                selected_row_id = tree_item_id

        if selected_row_id is None and self.session_tree.get_children():
            selected_row_id = self.session_tree.get_children()[0]

        if selected_row_id is not None:
            self.session_tree.selection_set(selected_row_id)
            self.session_tree.focus(selected_row_id)

    def _handle_sort_changed(self, _event: object) -> None:
        """Apply the selected sort settings to the session tree."""
        self._refresh_session_tree()
        self._handle_session_selected(None)

    def _handle_heading_sort(self, sort_key: str) -> None:
        """Apply or toggle sorting when a column heading is clicked."""
        current_sort_by = resolve_sort_by(self.sort_by_var.get())
        current_sort_order = resolve_sort_order(self.sort_order_var.get())

        next_sort_order = 'asc'
        if current_sort_by == sort_key:
            next_sort_order = 'asc' if current_sort_order == 'desc' else 'desc'

        self.sort_by_var.set(self._label_for_sort_by(sort_key))
        self.sort_order_var.set(self._label_for_sort_order(next_sort_order))
        self._refresh_session_tree()
        self._handle_session_selected(None)

    def _label_for_sort_by(self, sort_key: str) -> str:
        """Return the UI label for a sort key."""
        for label, key in SORT_BY_OPTIONS:
            if key == sort_key:
                return label
        return sort_key

    def _label_for_sort_order(self, sort_order: str) -> str:
        """Return the UI label for a sort order key."""
        for label, key in SORT_ORDER_OPTIONS:
            if key == sort_order:
                return label
        return sort_order

    def _build_detail_panel(self, parent: ttk.Frame) -> None:
        """Create the right placeholder pane."""
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 8))

        title_label = ttk.Label(header_frame, text='Details')
        title_label.pack(side=tk.LEFT)

        self.export_button = ttk.Button(
            header_frame,
            text='Markdown 保存',
            command=self._export_selected_session,
            state='disabled',
        )
        self.export_button.pack(side=tk.RIGHT)

        detail_frame = ttk.Frame(parent, relief=tk.GROOVE, padding=12)
        detail_frame.pack(fill=tk.BOTH, expand=True)

        detail_title = ttk.Label(detail_frame, textvariable=self.detail_var, justify=tk.LEFT, anchor=tk.W)
        detail_title.pack(fill=tk.X, pady=(0, 8))

        text_frame = ttk.Frame(detail_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)

        self.detail_text = tk.Text(text_frame, wrap='word', state='disabled')
        self.detail_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.detail_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.detail_text.configure(yscrollcommand=scrollbar.set)
        self.detail_text.tag_configure('heading_user', foreground='#0b57d0', spacing1=10, spacing3=2)
        self.detail_text.tag_configure('heading_assistant', foreground='#137333', spacing1=10, spacing3=2)
        self.detail_text.tag_configure('content', spacing3=10)
        self._set_detail_text('No session selected.')

    def _handle_session_selected(self, _event: object) -> None:
        """Update the placeholder detail pane from the selected list item."""
        selection = self.session_tree.selection()
        if not selection:
            self._selected_session_id = None
            self.export_button.configure(state='disabled')
            self.detail_var.set('No session selected.')
            self._set_detail_text('No session selected.')
            return

        session_id, title, message_count, latest, has_warnings = self._tree_item_to_session[selection[0]]
        warning_text = 'Yes' if has_warnings else 'No'
        session = self._sessions_by_id.get(session_id)
        self._selected_session_id = session_id
        self.export_button.configure(state='normal' if session is not None else 'disabled')
        self.detail_var.set(f'{title} | Messages: {message_count} | Latest: {latest} | Warnings: {warning_text}')
        if session is None:
            self._set_detail_text('The selected session could not be loaded.')
            return
        self._render_session_messages(session)

    def _export_selected_session(self) -> None:
        """Export the currently selected session to a Markdown file."""
        session = self._get_selected_session()
        if session is None:
            messagebox.showinfo('Markdown Export', 'No session is selected.')
            self.status_var.set('Markdown export skipped: no session selected.')
            return

        document = build_markdown_document(session)
        selected_path = filedialog.asksaveasfilename(
            title='Markdown エクスポート',
            defaultextension='.md',
            filetypes=[('Markdown files', '*.md'), ('All files', '*.*')],
            initialfile=document.suggested_filename,
        )
        if not selected_path:
            self.status_var.set('Markdown export cancelled.')
            return

        output_path = Path(selected_path)
        try:
            output_path.write_text(document.body, encoding='utf-8')
        except OSError as error:
            messagebox.showerror('Markdown Export', f'Failed to export Markdown: {error}')
            self.status_var.set(f'Markdown export failed: {output_path}')
            return

        self.status_var.set(f'Markdown exported: {output_path}')

    def _get_selected_session(self) -> Session | None:
        """Return the currently selected session, if available."""
        if self._selected_session_id is None:
            return None
        return self._sessions_by_id.get(self._selected_session_id)

    def _render_session_messages(self, session: Session) -> None:
        """Render actual session messages in the detail text pane."""
        self.detail_text.configure(state='normal')
        self.detail_text.delete('1.0', tk.END)

        if not session.messages:
            self.detail_text.insert('1.0', 'This session has no displayable messages.')
            self.detail_text.configure(state='disabled')
            return

        for message in session.messages:
            heading = build_message_heading(message)
            heading_tag = 'heading_user' if message.role is MessageRole.USER else 'heading_assistant'
            self.detail_text.insert(tk.END, f'{heading}\n', heading_tag)
            self.detail_text.insert(tk.END, f'{message.content}\n\n', 'content')

        self.detail_text.configure(state='disabled')
        self.detail_text.see('1.0')

    def _set_detail_text(self, value: str) -> None:
        """Replace the detail text content with plain text."""
        self.detail_text.configure(state='normal')
        self.detail_text.delete('1.0', tk.END)
        self.detail_text.insert('1.0', value)
        self.detail_text.configure(state='disabled')


__all__ = [
    'ChatLogViewerApp',
    'build_message_heading',
    'format_latest_timestamp',
    'format_message_timestamp',
    'format_warning_flag',
    'sort_session_list_items',
]
