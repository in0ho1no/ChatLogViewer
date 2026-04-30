"""Tests for the VS Code chat viewer parser."""

from __future__ import annotations

import json
import re
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vscode_chat_viewer import (
    ChatMessage,
    ChatSession,
    build_assistant_message_text,
    build_assistant_response_text,
    build_markdown,
    decode_file_uri,
    discover_chat_sessions,
    extract_text,
    extract_windows_username,
    format_timestamp,
    load_workspace_label,
    make_unique_filename,
    merge_response_fragments,
    parse_chat_session,
    resolve_workspace_open_path,
    sanitize_filename,
    shorten_text,
)

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


# ---------------------------------------------------------------------------
# parse_chat_session
# ---------------------------------------------------------------------------


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

        assert session.session_id == 'session-1'
        assert session.custom_title == 'Custom Title'
        assert session.model_id == 'copilot/test'
        assert session.preview_text == '最初の質問です'
        assert session.message_count == 4
        assert [message.role for message in session.messages] == ['user', 'assistant', 'user', 'assistant']
        assert session.messages[1].text == '最初の応答段落です。\n\n追加の応答です。'
        assert session.messages[3].text == '二つ目の応答です。'

        markdown = build_markdown(session)
        assert '# Chat Session' in markdown
        assert '## Metadata' in markdown
        assert '# Conversation' in markdown
        assert '## User' in markdown
        assert '## Assistant' in markdown
        assert '- User: `Unknown`' in markdown
        assert format_timestamp(1710000001000, '%Y/%m/%d %H:%M') in markdown
        assert '## 1. User' not in markdown

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

        assert session.message_count == 2
        assert session.parse_errors
        assert session.messages[0].text == '質問'
        assert session.messages[1].text == '応答'


# ---------------------------------------------------------------------------
# extract_text
# ---------------------------------------------------------------------------


class ExtractTextTests(unittest.TestCase):
    """Tests for the extract_text helper."""

    def test_none_returns_empty(self) -> None:
        """None input should yield an empty string."""
        assert extract_text(None) == ''

    def test_string_returned_as_is(self) -> None:
        """A plain string should pass through unchanged."""
        assert extract_text('hello') == 'hello'

    def test_dict_with_text_key(self) -> None:
        """A dict containing 'text' should return that value."""
        assert extract_text({'text': 'hi'}) == 'hi'

    def test_dict_with_value_key(self) -> None:
        """A dict without 'text' but with 'value' should return that value."""
        assert extract_text({'value': 'val'}) == 'val'

    def test_dict_with_parts_list(self) -> None:
        """A dict with 'parts' should join each part's text."""
        assert extract_text({'parts': [{'text': 'A'}, {'text': 'B'}]}) == 'AB'

    def test_list_of_strings(self) -> None:
        """A list of strings should be joined."""
        assert extract_text(['foo', 'bar']) == 'foobar'

    def test_unknown_type_returns_empty(self) -> None:
        """Numeric values should yield an empty string."""
        assert extract_text(42) == ''

    def test_depth_limit_stops_recursion(self) -> None:
        """Deeply nested structures must not raise RecursionError; truncation is acceptable."""
        # Build a 200-level deep parts chain — well beyond _EXTRACT_TEXT_MAX_DEPTH.
        deep: dict = {'text': 'leaf'}
        for _ in range(200):
            deep = {'parts': [deep]}
        # Must not raise; result may be empty due to depth cap.
        result = extract_text(deep)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# load_workspace_label
# ---------------------------------------------------------------------------


class LoadWorkspaceLabelTests(unittest.TestCase):
    """Tests for load_workspace_label."""

    def test_missing_file_returns_dir_string(self) -> None:
        """A missing workspace.json should fall back to the directory path."""
        with WorkspaceTempDir() as workspace_dir:
            assert load_workspace_label(workspace_dir) == str(workspace_dir)

    def test_malformed_json_returns_dir_string(self) -> None:
        """A workspace.json with invalid JSON should fall back to the directory path."""
        with WorkspaceTempDir() as workspace_dir:
            (workspace_dir / 'workspace.json').write_text('{invalid', encoding='utf-8')
            assert load_workspace_label(workspace_dir) == str(workspace_dir)

    def test_non_dict_json_returns_dir_string(self) -> None:
        """A workspace.json whose root value is not a dict must not raise AttributeError."""
        with WorkspaceTempDir() as workspace_dir:
            (workspace_dir / 'workspace.json').write_text('[]', encoding='utf-8')
            # Before the fix this raised AttributeError; now it must return safely.
            assert load_workspace_label(workspace_dir) == str(workspace_dir)

    def test_folder_key_decoded_and_returned(self) -> None:
        """A 'folder' file URI should be decoded and returned as the label."""
        with WorkspaceTempDir() as workspace_dir:
            (workspace_dir / 'workspace.json').write_text(
                json.dumps({'folder': 'file:///d%3A/work/project'}),
                encoding='utf-8',
            )
            assert load_workspace_label(workspace_dir) == 'D:\\work\\project'

    def test_no_known_keys_returns_dir_string(self) -> None:
        """A workspace.json without folder/workspace/configuration falls back to the dir."""
        with WorkspaceTempDir() as workspace_dir:
            (workspace_dir / 'workspace.json').write_text(json.dumps({'other': 'value'}), encoding='utf-8')
            assert load_workspace_label(workspace_dir) == str(workspace_dir)


# ---------------------------------------------------------------------------
# shorten_text
# ---------------------------------------------------------------------------


class ShortenTextTests(unittest.TestCase):
    """Tests for shorten_text."""

    def test_empty_string(self) -> None:
        """Empty input should produce an empty string."""
        assert shorten_text('', 10) == ''

    def test_short_string_unchanged(self) -> None:
        """Strings at or below the limit are returned as-is."""
        assert shorten_text('hello', 10) == 'hello'

    def test_exact_limit_unchanged(self) -> None:
        """A string exactly at the character limit should not be truncated."""
        assert shorten_text('1234567890', 10) == '1234567890'

    def test_over_limit_truncated_with_ellipsis(self) -> None:
        """Strings longer than the limit should gain an ellipsis suffix."""
        result = shorten_text('1234567890X', 10)
        assert result == '1234567890...'

    def test_multiple_spaces_compacted(self) -> None:
        """Internal whitespace runs should be collapsed to a single space."""
        assert shorten_text('a  b   c', 20) == 'a b c'


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------


class SanitizeFilenameTests(unittest.TestCase):
    """Tests for sanitize_filename."""

    def test_invalid_chars_replaced_with_underscore(self) -> None:
        """Windows-forbidden characters should be replaced with underscores."""
        assert sanitize_filename('file<>:"/\\|?*name') == 'file_________name'

    def test_control_chars_stripped(self) -> None:
        """Control characters (U+0000–U+001F) must be removed entirely."""
        assert sanitize_filename('ab\x00\x1fc') == 'abc'

    def test_reserved_name_prefixed(self) -> None:
        """Bare Windows reserved names should receive a leading underscore."""
        for name in ('CON', 'NUL', 'PRN', 'AUX', 'COM1', 'LPT9'):
            with self.subTest(name=name):
                result = sanitize_filename(name)
                assert result.startswith('_'), f'Expected _ prefix for {name!r}, got {result!r}'

    def test_reserved_name_with_extension_prefixed(self) -> None:
        """Reserved names followed by a dot extension must also be prefixed."""
        assert sanitize_filename('NUL.txt').startswith('_')

    def test_non_reserved_name_not_prefixed(self) -> None:
        """Ordinary names must not receive an extra prefix."""
        result = sanitize_filename('session')
        assert result == 'session'

    def test_truncated_to_120_chars(self) -> None:
        """Results longer than 120 characters must be truncated."""
        long_name = 'a' * 200
        assert len(sanitize_filename(long_name)) == 120

    def test_empty_input_returns_empty(self) -> None:
        """Empty input should produce an empty string."""
        assert sanitize_filename('') == ''


# ---------------------------------------------------------------------------
# resolve_workspace_open_path
# ---------------------------------------------------------------------------


class ResolveWorkspaceOpenPathTests(unittest.TestCase):
    """Tests for resolve_workspace_open_path."""

    def test_returns_existing_directory(self) -> None:
        """An existing directory path should be resolved successfully."""
        resolved = resolve_workspace_open_path(str(Path(__file__).resolve().parent))
        assert resolved is not None
        assert resolved.is_dir()

    def test_returns_none_for_nonexistent_path(self) -> None:
        """A path that does not exist on disk should return None."""
        assert resolve_workspace_open_path('C:\\does\\not\\exist\\__x__') is None

    def test_returns_code_workspace_file(self) -> None:
        """An existing .code-workspace file should be accepted."""
        with WorkspaceTempDir() as tmp:
            ws_file = tmp / 'project.code-workspace'
            ws_file.write_text('{}', encoding='utf-8')
            resolved = resolve_workspace_open_path(str(ws_file))
            assert resolved == ws_file

    def test_rejects_executable_file(self) -> None:
        """An existing file with an unsafe extension must return None."""
        with WorkspaceTempDir() as tmp:
            exe = tmp / 'malicious.bat'
            exe.write_text('@echo off', encoding='utf-8')
            assert resolve_workspace_open_path(str(exe)) is None

    def test_empty_string_returns_none(self) -> None:
        """An empty workspace path should return None without raising."""
        assert resolve_workspace_open_path('') is None


# ---------------------------------------------------------------------------
# discover_chat_sessions
# ---------------------------------------------------------------------------


class DiscoverChatSessionsTests(unittest.TestCase):
    """Tests for discover_chat_sessions."""

    def _write_minimal_jsonl(self, path: Path, session_id: str, timestamp: int, question: str) -> None:
        """Write a minimal JSONL session file to *path*."""
        lines = [
            json.dumps({'kind': 0, 'v': {'version': 3, 'creationDate': timestamp, 'sessionId': session_id}}, ensure_ascii=False),
            json.dumps(
                {
                    'kind': 2,
                    'k': ['requests'],
                    'v': [{'requestId': 'r1', 'timestamp': timestamp, 'message': {'text': question}, 'response': [{'value': '応答'}]}],
                },
                ensure_ascii=False,
            ),
        ]
        path.write_text('\n'.join(lines), encoding='utf-8')

    def test_returns_empty_for_missing_storage(self) -> None:
        """An absent workspaceStorage directory should yield an empty list."""
        with WorkspaceTempDir() as tmp:
            assert discover_chat_sessions(user_root=tmp) == []

    def test_skips_workspace_without_chat_sessions(self) -> None:
        """A workspace directory that has no chatSessions folder is silently skipped."""
        with WorkspaceTempDir() as tmp:
            (tmp / 'workspaceStorage' / 'abc123').mkdir(parents=True)
            assert discover_chat_sessions(user_root=tmp) == []

    def test_finds_sessions_sorted_by_updated_at_descending(self) -> None:
        """Sessions should be returned newest-first."""
        with WorkspaceTempDir() as tmp:
            for ws_id, ts, q in [
                ('ws1', 1710000001000, '古い質問'),
                ('ws2', 1710000003000, '新しい質問'),
                ('ws3', 1710000002000, '中間の質問'),
            ]:
                chat_dir = tmp / 'workspaceStorage' / ws_id / 'chatSessions'
                chat_dir.mkdir(parents=True)
                self._write_minimal_jsonl(chat_dir / 'session.jsonl', ws_id, ts, q)

            sessions = discover_chat_sessions(user_root=tmp)

        assert len(sessions) == 3
        assert sessions[0].preview_text == '新しい質問'
        assert sessions[1].preview_text == '中間の質問'
        assert sessions[2].preview_text == '古い質問'

    def test_skips_empty_sessions_without_title(self) -> None:
        """Sessions with no messages and no custom title should be filtered out."""
        with WorkspaceTempDir() as tmp:
            chat_dir = tmp / 'workspaceStorage' / 'ws1' / 'chatSessions'
            chat_dir.mkdir(parents=True)
            # Write a JSONL with only metadata, no requests.
            (chat_dir / 'empty.jsonl').write_text(
                json.dumps({'kind': 0, 'v': {'version': 3, 'sessionId': 'empty'}}),
                encoding='utf-8',
            )
            assert discover_chat_sessions(user_root=tmp) == []


# ---------------------------------------------------------------------------
# merge_response_fragments
# ---------------------------------------------------------------------------


class MergeResponseFragmentsTests(unittest.TestCase):
    """Tests for merge_response_fragments (internal helper)."""

    def test_empty_existing_returns_fragment(self) -> None:
        """When existing is empty the fragment is returned directly."""
        assert merge_response_fragments('', 'hello') == 'hello'

    def test_fragment_that_extends_existing(self) -> None:
        """A fragment that starts with existing should replace it (streaming update)."""
        assert merge_response_fragments('hello', 'hello world') == 'hello world'

    def test_existing_absorbs_duplicate_tail(self) -> None:
        """A fragment already present at the end of existing is dropped."""
        assert merge_response_fragments('hello world', 'world') == 'hello world'

    def test_partial_overlap_joined_without_duplication(self) -> None:
        """Overlapping suffix/prefix should be merged without repeating the shared part."""
        result = merge_response_fragments('abcde', 'cdefg')
        assert result == 'abcdefg'

    def test_no_overlap_appended_directly(self) -> None:
        """Non-overlapping fragments with no sentence-end marker are concatenated."""
        result = merge_response_fragments('hello ', 'world')
        assert result == 'hello world'

    def test_paragraph_break_after_japanese_sentence_end(self) -> None:
        """A new fragment after a 。-terminated existing should insert a paragraph break."""
        result = merge_response_fragments('文章です。', '次の段落。')
        assert '\n\n' in result


# ---------------------------------------------------------------------------
# build_markdown edge cases
# ---------------------------------------------------------------------------


class BuildMarkdownTests(unittest.TestCase):
    """Edge-case tests for build_markdown."""

    def _make_session(self, **kwargs) -> ChatSession:  # type: ignore[no-untyped-def]
        """Build a minimal ChatSession for testing."""
        defaults: dict = {
            'session_id': 'test-id',
            'session_path': Path('C:/fake/session.jsonl'),
            'workspace_path': 'C:/fake/workspace',
            'workspace_storage_path': Path('C:/fake'),
            'created_at_ms': None,
            'updated_at_ms': None,
            'preview_text': '',
            'custom_title': None,
            'responder_username': None,
            'model_id': None,
        }
        defaults.update(kwargs)
        return ChatSession(**defaults)

    def test_no_messages_shows_placeholder(self) -> None:
        """A session with no messages should include a placeholder notice."""
        session = self._make_session()
        md = build_markdown(session)
        assert '_No chat messages could be reconstructed from this session._' in md

    def test_parse_errors_section_present(self) -> None:
        """Parse warnings should appear in a dedicated section."""
        session = self._make_session()
        session.parse_errors.append('Line 3: Expecting value')
        md = build_markdown(session)
        assert '# Parse Warnings' in md
        assert 'Line 3: Expecting value' in md

    def test_model_id_included_in_metadata(self) -> None:
        """A session with a model_id should include it in the Metadata section."""
        session = self._make_session(model_id='copilot/gpt-4o')
        md = build_markdown(session)
        assert '`copilot/gpt-4o`' in md

    def test_messages_rendered_with_correct_headings(self) -> None:
        """User and assistant headings must appear without sequence numbers."""
        session = self._make_session()
        session.messages.append(ChatMessage(role='user', text='質問'))
        session.messages.append(ChatMessage(role='assistant', text='回答'))
        md = build_markdown(session)
        assert '## User' in md
        assert '## Assistant' in md
        assert '## 1. User' not in md


# ---------------------------------------------------------------------------
# Helper function tests (misc)
# ---------------------------------------------------------------------------


class HelperFunctionTests(unittest.TestCase):
    """Tests for helper functions."""

    def test_format_timestamp_for_list_includes_time(self) -> None:
        """List timestamps should keep date and time."""
        formatted = format_timestamp(1710000000000, '%Y/%m/%d %H:%M')
        assert re.match(r'^\d{4}/\d{2}/\d{2} \d{2}:\d{2}$', formatted)

    def test_decode_file_uri_for_windows_drive_path(self) -> None:
        """A VS Code file URI should decode into a Windows path."""
        decoded = decode_file_uri('file:///d%3A/work/project')
        assert decoded == 'D:\\work\\project'

    def test_decode_file_uri_unc_path(self) -> None:
        """A file URI with a netloc should produce a UNC path."""
        decoded = decode_file_uri('file://server/share/file.txt')
        assert decoded.startswith('\\\\server')

    def test_decode_file_uri_non_file_scheme_returned_as_is(self) -> None:
        """A non-file URI scheme should be returned unchanged."""
        uri = 'vscode-remote://ssh-remote+host/home/user/project'
        assert decode_file_uri(uri) == uri

    def test_decode_file_uri_empty_returns_empty(self) -> None:
        """An empty URI should return an empty string."""
        assert decode_file_uri('') == ''

    def test_extract_windows_username_from_user_profile_path(self) -> None:
        """Windows profile paths should expose the username."""
        username = extract_windows_username(Path(r'C:\Users\seigy\AppData\Roaming\Code\User\workspaceStorage\a\chatSessions\b.jsonl'))
        assert username == 'seigy'

    def test_make_unique_filename_adds_suffix(self) -> None:
        """Bulk export filenames should be deduplicated predictably."""
        used_names = {'session.md', 'session (2).md'}
        assert make_unique_filename('session', used_names) == 'session (3).md'

    def test_build_assistant_response_text_merges_inline_references_and_overlaps(self) -> None:
        """Visible fragments should keep inline references and absorb overlapping tails."""
        text = build_assistant_response_text(
            [
                {'value': '重大な指摘はありませんでした。'},
                {'kind': 'inlineReference', 'name': 'src/mtpj_deps.py'},
                {'value': ' では XML の安全化が入っており、'},
                {'kind': 'inlineReference', 'name': 'SECURITY.md'},
                {'value': ' でも注意が追加されています。uv run pytest src/tests -q は 86 passed で、'},
                {'kind': 'inlineReference', 'name': 'src/mtpj_deps.py'},
                {'value': ' と '},
                {'kind': 'inlineReference', 'name': 'src/tests/test_mtpj_deps.py'},
                {'value': ' に静的エラーもありませんでした。\n\n'},
                {'value': ' に静的エラーもありませんでした。\n\n残る注意点があります。'},
            ],
        )
        assert '`src/mtpj_deps.py` では XML の安全化が入っており、`SECURITY.md` でも注意が追加されています。' in text
        assert '`src/mtpj_deps.py` と `src/tests/test_mtpj_deps.py` に静的エラーもありませんでした。' in text
        assert text.count('に静的エラーもありませんでした。') == 1

    def test_build_assistant_message_text_prefers_clean_tool_round_responses(self) -> None:
        """Cleaner tool round responses should be preferred over broken progress fragments."""
        request = {
            'result': {
                'metadata': {
                    'toolCallRounds': [
                        {'response': 'まず変更ファイルを把握してから、`SECURITY.md` と実装の該当箇所を突き合わせます。'},
                        {
                            'response': (
                                'テストで安全性の回帰がないかを確認します。`SECURITY.md` だけでなく、'
                                'XML・出力サニタイズ・既存機能の回帰もまとめて見ます。'
                            )
                        },
                    ]
                }
            },
            'response': [
                {'value': 'まず変更ファイルを把握してから、'},
                {'value': ' と実装の該当箇所を突き合わせます。'},
                {'kind': 'thinking', 'value': 'internal'},
                {'value': '重大な指摘はありませんでした。'},
            ],
        }
        text = build_assistant_message_text(request)
        assert '`SECURITY.md` と実装の該当箇所を突き合わせます。' in text
        assert '重大な指摘はありませんでした。' in text

    def test_build_assistant_message_text_avoids_duplicate_final_answer(self) -> None:
        """A final answer already present in cleaner progress text should not be appended twice."""
        request = {
            'result': {
                'metadata': {
                    'toolCallRounds': [
                        {
                            'response': (
                                '重大な指摘はありませんでした。[src/mtpj_deps.py](src/mtpj_deps.py) と [SECURITY.md](SECURITY.md) を確認しました。'
                            )
                        }
                    ]
                }
            },
            'response': [
                {'kind': 'thinking', 'value': 'internal'},
                {'value': '重大な指摘はありませんでした。`src/mtpj_deps.py` と `SECURITY.md` を確認しました。'},
            ],
        }
        text = build_assistant_message_text(request)
        assert text.count('重大な指摘はありませんでした。') == 1


if __name__ == '__main__':
    unittest.main()
