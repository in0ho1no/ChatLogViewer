"""Tkinter UI for the chat log viewer prototype."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from scanner import collect_scan_issues, scan_sessions, summarize_scan
from session_list import build_session_list_items


def format_latest_timestamp(value: object) -> str:
    """Format the latest timestamp for the session list."""
    if value is None:
        return 'n/a'
    iso_value = getattr(value, 'isoformat', None)
    if callable(iso_value):
        return str(iso_value(timespec='seconds'))
    return str(value)


def format_warning_flag(has_warnings: bool) -> str:
    """Format the warning state for the session list."""
    return 'yes' if has_warnings else 'no'


class ChatLogViewerApp:
    """Minimal Tkinter application shell for browsing scanned sessions."""

    def __init__(self, root: tk.Tk) -> None:
        """Initialize the UI widgets."""
        self.root = root
        self.root.title('Chat Log Viewer')
        self.root.geometry('1200x720')

        self._tree_item_to_session: dict[str, tuple[str, str, int, str, bool]] = {}

        self.status_var = tk.StringVar(value='Ready')
        self.detail_var = tk.StringVar(value='No session selected.')

        self._build_layout()

    def load_sessions(self, root_dir: Path) -> None:
        """Scan sessions and populate the left-hand session list."""
        self.status_var.set(f'Scanning sessions under {root_dir}...')
        self.root.update_idletasks()

        sessions = scan_sessions(root_dir)
        list_items = build_session_list_items(sessions)
        session_count, warning_count = summarize_scan(sessions)
        issues = collect_scan_issues(sessions)

        self.session_tree.delete(*self.session_tree.get_children())
        self._tree_item_to_session.clear()

        for item in list_items:
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

        issue_count = len(issues)
        self.status_var.set(f'Sessions: {session_count}  Warnings: {warning_count}  Issues: {issue_count}  Root: {root_dir}')

        if list_items:
            first_item = self.session_tree.get_children()[0]
            self.session_tree.selection_set(first_item)
            self._handle_session_selected(None)
        else:
            self.detail_var.set('No sessions found.')

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

        columns = ('messages', 'latest', 'warnings')
        self.session_tree = ttk.Treeview(parent, columns=columns, show='tree headings', selectmode='browse')
        self.session_tree.heading('#0', text='Title')
        self.session_tree.heading('messages', text='Messages')
        self.session_tree.heading('latest', text='Latest')
        self.session_tree.heading('warnings', text='Warnings')
        self.session_tree.column('#0', width=360, anchor=tk.W)
        self.session_tree.column('messages', width=90, anchor=tk.E)
        self.session_tree.column('latest', width=180, anchor=tk.W)
        self.session_tree.column('warnings', width=80, anchor=tk.CENTER)
        self.session_tree.pack(fill=tk.BOTH, expand=True)
        self.session_tree.bind('<<TreeviewSelect>>', self._handle_session_selected)

    def _build_detail_panel(self, parent: ttk.Frame) -> None:
        """Create the right placeholder pane."""
        title_label = ttk.Label(parent, text='Details')
        title_label.pack(anchor=tk.W, pady=(0, 8))

        detail_frame = ttk.Frame(parent, relief=tk.GROOVE, padding=12)
        detail_frame.pack(fill=tk.BOTH, expand=True)

        detail_label = ttk.Label(
            detail_frame,
            textvariable=self.detail_var,
            justify=tk.LEFT,
            anchor=tk.NW,
            wraplength=540,
        )
        detail_label.pack(fill=tk.BOTH, expand=True)

    def _handle_session_selected(self, _event: object) -> None:
        """Update the placeholder detail pane from the selected list item."""
        selection = self.session_tree.selection()
        if not selection:
            self.detail_var.set('No session selected.')
            return

        session_id, title, message_count, latest, has_warnings = self._tree_item_to_session[selection[0]]
        warning_text = 'Yes' if has_warnings else 'No'
        self.detail_var.set(
            '\n'.join(
                [
                    f'Title: {title}',
                    f'Session ID: {session_id}',
                    f'Messages: {message_count}',
                    f'Latest activity: {latest}',
                    f'Warnings: {warning_text}',
                    '',
                    'Right pane is currently a placeholder. The full transcript view will be connected next.',
                ]
            )
        )


__all__ = ['ChatLogViewerApp', 'format_latest_timestamp', 'format_warning_flag']
