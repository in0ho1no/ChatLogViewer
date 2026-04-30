"""Tests for the VS Code chat viewer parser."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vscode_chat_viewer import build_markdown, decode_file_uri, make_unique_filename, parse_chat_session


TEST_TMP_ROOT = Path(__file__).resolve().parent / '_tmp'


class WorkspaceTempDir:
    """A small temporary directory helper rooted inside the workspace."""

    def __enter__(self) -> Path:
        """Create and return a writable temporary directory."""
        self.path = TEST_TMP_ROOT / uuid.uuid4().hex
        self.path.mkdir(parents=True, exist_ok=False)
        return self.path

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Clean up the temporary directory recursively."""
        if not hasattr(self, 'path'):
            return
        for child in sorted(self.path.rglob('*'), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        self.path.rmdir()


class ParseChatSessionTests(unittest.TestCase):
    """Tests for JSONL session parsing."""

    def test_parse_session_collects_requests_and_response_appends(self) -> None:
        """The parser should rebuild turns from request and response append events."""
        with WorkspaceTempDir() as workspace_dir:
            session_path = workspace_dir / 'sample.jsonl'
            lines = [
                {
                    'kind': 0,
                    'v': {
                        'version': 3,
                        'creationDate': 1710000000000,
                        'sessionId': 'session-1',
                        'responderUsername': 'GitHub Copilot',
                    },
                },
                {'kind': 1, 'k': ['inputState', 'inputText'], 'v': '途中入力'},
                {'kind': 1, 'k': ['customTitle'], 'v': 'Custom Title'},
                {
                    'kind': 2,
                    'k': ['requests'],
                    'v': [
                        {
                            'requestId': 'req-1',
                            'timestamp': 1710000001000,
                            'message': {'text': '最初の質問です'},
                            'modelId': 'copilot/test',
                            'response': [
                                {'kind': 'thinking', 'value': 'internal'},
                                {'value': '最初の応答段落です。'},
                            ],
                        }
                    ],
                },
                {
                    'kind': 2,
                    'k': ['requests', 0, 'response'],
                    'v': [
                        {'value': '最初の応答段落です。'},
                        {'value': '追加の応答です。'},
                    ],
                },
                {'kind': 1, 'k': ['inputState', 'inputText'], 'v': '二つ目の途中入力'},
                {
                    'kind': 2,
                    'k': ['requests'],
                    'v': [
                        {
                            'requestId': 'req-2',
                            'timestamp': 1710000002000,
                            'message': {'text': '二つ目の質問です'},
                            'response': [],
                        }
                    ],
                },
                {
                    'kind': 2,
                    'k': ['requests', 1, 'response'],
                    'v': [
                        {'kind': 'progressTaskSerialized', 'value': 'progress'},
                        {'value': '二つ目の応答です。'},
                    ],
                },
            ]
            session_path.write_text('\n'.join(json.dumps(line, ensure_ascii=False) for line in lines), encoding='utf-8')

            session = parse_chat_session(session_path, 'D:\\work\\sample', workspace_dir)

        self.assertEqual(session.session_id, 'session-1')
        self.assertEqual(session.custom_title, 'Custom Title')
        self.assertEqual(session.model_id, 'copilot/test')
        self.assertEqual(session.preview_text, '最初の質問です')
        self.assertEqual(session.message_count, 4)
        self.assertEqual([message.role for message in session.messages], ['user', 'assistant', 'user', 'assistant'])
        self.assertEqual(session.messages[1].text, '最初の応答段落です。\n\n追加の応答です。')
        self.assertEqual(session.messages[3].text, '二つ目の応答です。')

        markdown = build_markdown(session)
        self.assertIn('# Chat Session', markdown)
        self.assertIn('## Metadata', markdown)
        self.assertIn('# Conversation', markdown)
        self.assertIn('## User', markdown)
        self.assertIn('## Assistant', markdown)
        self.assertNotIn('## 1. User', markdown)

    def test_parse_session_skips_broken_tail_line(self) -> None:
        """The parser should keep earlier messages even if the final line is truncated."""
        with WorkspaceTempDir() as workspace_dir:
            session_path = workspace_dir / 'broken.jsonl'
            valid_line = json.dumps(
                {
                    'kind': 0,
                    'v': {
                        'version': 3,
                        'creationDate': 1710000000000,
                        'sessionId': 'broken-session',
                    },
                },
                ensure_ascii=False,
            )
            request_line = json.dumps(
                {
                    'kind': 2,
                    'k': ['requests'],
                    'v': [
                        {
                            'requestId': 'req-1',
                            'timestamp': 1710000001000,
                            'message': {'text': '質問'},
                            'response': [{'value': '応答'}],
                        }
                    ],
                },
                ensure_ascii=False,
            )
            session_path.write_text(valid_line + '\n' + request_line + '\n{"kind": 2, "k": ["requests"', encoding='utf-8')

            session = parse_chat_session(session_path, 'D:\\work\\sample', workspace_dir)

        self.assertEqual(session.message_count, 2)
        self.assertTrue(session.parse_errors)
        self.assertEqual(session.messages[0].text, '質問')
        self.assertEqual(session.messages[1].text, '応答')


class HelperFunctionTests(unittest.TestCase):
    """Tests for helper functions."""

    def test_decode_file_uri_for_windows_drive_path(self) -> None:
        """A VS Code file URI should decode into a Windows path."""
        decoded = decode_file_uri('file:///d%3A/work/project')
        self.assertEqual(decoded, 'D:\\work\\project')

    def test_make_unique_filename_adds_suffix(self) -> None:
        """Bulk export filenames should be deduplicated predictably."""
        used_names = {'session.md', 'session (2).md'}
        self.assertEqual(make_unique_filename('session', used_names), 'session (3).md')


if __name__ == '__main__':
    unittest.main()
