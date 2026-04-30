# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## アプリケーション概要

**ChatLogViewer** は、VS Code がローカルに保存したチャットセッションログ（JSONL形式）を読み込み、Tkinter UIで閲覧・Markdown形式でエクスポートする Windows 11 専用のデスクトップアプリ。

- **データソース**: `%APPDATA%\Code\User\workspaceStorage\*\chatSessions\*.jsonl`
- **技術スタック**: Python 3.12+、Tkinter（標準ライブラリのみ、外部依存なし）
- **パッケージ管理**: `uv`

## アーキテクチャ

コアロジックとUIは `src/vscode_chat_viewer.py` 1ファイルに集約されている。`src/main.py` はエントリポイントのみ。

### 主要な構成要素

| 要素 | 説明 |
|------|------|
| `ChatMessage` | 1メッセージ（role, text, timestamp） |
| `ChatSession` | セッション全体（メッセージリスト＋メタデータ） |
| `discover_chat_sessions()` | VS Code ストレージを走査してセッションを収集 |
| `parse_chat_session()` | JSONL ファイルをパース。ストリーミング断片を統合 |
| `build_markdown()` | セッションを Markdown テキストに変換 |
| `ChatLogViewerApp` | Tkinter メインクラス。左ペイン（一覧）＋右ペイン（詳細） |

### データフロー

1. `discover_chat_sessions()` → ワークスペースディレクトリを走査
2. `parse_chat_session()` → JSONL を行単位で読み込み、アシスタント応答のストリーミング断片を結合
3. `ChatLogViewerApp` → セッション選択時に右ペインへ表示
4. エクスポート → `build_markdown()` で `.md` ファイルに保存

## コマンド

```bash
# アプリ起動
uv run python src/main.py

# コード品質（変更後は必ず実行）
uv run ruff check src/
uv run ruff format src/
uv run mypy src/

# テスト
uv run pytest                  # 全テスト
uv run pytest src/tests/test_vscode_chat_viewer.py::関数名  # 単体テスト
```

## 共通ルール

- 大きな変更の前には、短い計画を提示して確認を取る
- 次の変更は事前確認を必須とする
	- 依存パッケージの追加
	- 破壊的変更
	- 複数ファイルにまたがる大規模リファクタ
	- 設定ファイルや開発フローの変更
- 変更後は影響範囲に応じて必要最小限の検証を行う

## Python利用時の注意事項

### パッケージ追加について

- ライブラリ・パッケージを勝手に追加することは禁止
- pipコマンドを直接利用することは禁止
- パッケージ追加が必要な場合はユーザーに確認し、承認を得た上で `uv add <package>` を使用する

### コーディング時の注意点

- コーディング規約（型ヒント・docstringスタイル・命名規則など）は `pyproject.toml` に定義されているため参照すること
- ツールで自動検出できないルールとして、必要な変数には型ヒントを付けること
- uvで仮想環境を構築してあるので、Pythonスクリプトを実行する場合は`uv run`を利用する
- ファイルパスの操作は `os.path` ではなく `pathlib.Path` を使用する

### コード品質チェック

- Ruff（lint）: `uv run ruff check src/`
- Ruff（format）: `uv run ruff format src/`
- mypy: `uv run mypy src/`
- コード変更後は必ず上記を実行してエラーがないことを確認する

### テスト

- テストフレームワークは pytest を使用する
- テストファイルは `src/tests/` ディレクトリに配置し、`test_*.py` の命名規則に従う
- 実行: `uv run pytest`
