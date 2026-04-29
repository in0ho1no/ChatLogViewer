"""Entry point for the chat log viewer prototype."""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

from scanner import get_default_user_data_root
from ui import ChatLogViewerApp


def main(target_dir: Path | None = None) -> None:
    """Start the Tkinter application and load the initial session list."""
    root_dir = target_dir or get_default_user_data_root()
    root = tk.Tk()
    app = ChatLogViewerApp(root)
    root.after(0, lambda: app.load_sessions(root_dir))
    root.mainloop()


if __name__ == '__main__':
    cli_target = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    main(cli_target)
