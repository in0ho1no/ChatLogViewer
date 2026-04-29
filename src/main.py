"""Entry point for the chat log viewer prototype."""

from __future__ import annotations

import sys
from pathlib import Path

from scanner import get_default_user_data_root, scan_sessions, summarize_scan
from session_list import build_session_list_items


def main(target_dir: Path | None = None) -> None:
    """Scan transcript files and print a simple session list summary."""
    root_dir = target_dir or get_default_user_data_root()
    sessions = scan_sessions(root_dir)
    session_count, warning_count = summarize_scan(sessions)
    list_items = build_session_list_items(sessions)

    print(f'Scan root: {root_dir}')
    print(f'Sessions found: {session_count}')
    print(f'Sessions with warnings: {warning_count}')

    for item in list_items:
        latest_timestamp = item.latest_timestamp.isoformat() if item.latest_timestamp else 'n/a'
        print(
            f'- {item.display_title} '
            f'(session_id={item.session_id}, messages={item.message_count}, latest={latest_timestamp}, warnings={item.has_warnings})'
        )


if __name__ == '__main__':
    cli_target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    main(cli_target)
