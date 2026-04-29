# データモデル設計

## 目的

本書は、GitHub Copilot Chat 履歴ビューアの実装に必要なデータモデルを定義する。

目的は以下の 3 点である。

* 複数の入力ソースを、破壊せずに単一の正規化モデルへ統合する。
* UI 表示と Markdown エクスポートが、同じドメインモデルを共有できるようにする。
* パーサ、統合処理、UI 層の責務境界を明確にする。

元データは読み取り専用で扱い、入力ファイルを更新するモデルは定義しない。

## 設計方針

* 主記録は transcript JSONL とする。
* セッションの主キーは `session_id` とする。
* 補助メタデータは本文を上書きせず、正規化後の `Session` に追加マージする。
* UI 用の整形はドメインモデルの外側で行い、パーサは表示都合を持ち込まない。
* 一部データ破損時でも復旧可能なように、エラーと警告をモデル化する。

## モデル層

本実装では、データモデルを以下の 4 層に分ける。

1. 入力モデル
   JSONL、JSON、SQLite から直接読み出した生データ。
2. 正規化ドメインモデル
   ソース差異を吸収したアプリケーション内部の標準表現。
3. UI 表示モデル
   一覧・詳細表示に最適化した派生モデル。
4. エクスポートモデル
   Markdown 出力に必要な派生モデル。

## 入力モデル

### TranscriptFile

JSONL ファイル全体を表す読み込み単位。

| フィールド | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `file_path` | `Path` | 必須 | 読み込み元ファイル |
| `session_id` | `str` | 必須 | ファイル名と `session.start` から得た識別子 |
| `events` | `list[TranscriptEvent]` | 必須 | 読み込めたイベント行 |
| `issues` | `list[ParseIssue]` | 必須 | 読み込み中に発生した問題 |

### TranscriptEvent

JSONL の 1 行に対応するイベント。

| フィールド | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `event_id` | `str` | 必須 | JSONL の `id` |
| `event_type` | `str` | 必須 | JSONL の `type` |
| `timestamp` | `datetime | None` | 任意 | JSONL の `timestamp` を変換した値 |
| `parent_event_id` | `str | None` | 任意 | JSONL の `parentId` |
| `raw_data` | `dict[str, object]` | 必須 | `data` の生値 |
| `raw_line` | `str` | 必須 | 復旧や診断のため保持する元行 |
| `line_number` | `int` | 必須 | ファイル内行番号 |

### SessionMetadataSource

補助 JSON メタデータを読み込んだ結果。

| フィールド | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `session_id` | `str` | 必須 | 対象セッション ID |
| `title` | `str | None` | 任意 | カスタムタイトル等 |
| `first_user_message` | `str | None` | 任意 | セッション先頭の要約に使える値 |
| `workspace_folder` | `str | None` | 任意 | 補助的なワークスペース情報 |
| `repository_path` | `str | None` | 任意 | 補助的なリポジトリ情報 |
| `raw_payload` | `dict[str, object]` | 必須 | 将来拡張に備えた生値 |

### LegacySessionSource

SQLite から復元したレガシー入力。

| フィールド | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `storage_key` | `str` | 必須 | `ItemTable` のキー |
| `session_id` | `str | None` | 任意 | 抽出できた場合のセッション ID |
| `raw_json` | `str` | 必須 | JSON 文字列 |
| `parsed_payload` | `dict[str, object] | None` | 任意 | 解釈できた場合の値 |
| `issues` | `list[ParseIssue]` | 必須 | 読み取り時の問題 |

## 正規化ドメインモデル

### Session

アプリケーションが扱う標準的なセッション表現。

| フィールド | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `session_id` | `str` | 必須 | セッション主キー |
| `title` | `str` | 必須 | 表示用タイトル。補助メタデータがなければ本文から生成 |
| `messages` | `list[Message]` | 必須 | 時系列順の本文メッセージ |
| `started_at` | `datetime | None` | 任意 | セッション開始時刻 |
| `ended_at` | `datetime | None` | 任意 | セッション終端時刻 |
| `latest_timestamp` | `datetime | None` | 任意 | 一覧既定ソート用 |
| `oldest_timestamp` | `datetime | None` | 任意 | 代替ソート用 |
| `source_kind` | `SessionSourceKind` | 必須 | 主たる復元元 |
| `metadata` | `SessionMetadata` | 必須 | 補助情報の統合結果 |
| `issues` | `list[ParseIssue]` | 必須 | 当該セッションに紐づく問題 |

### Message

表示対象となる発話単位。

| フィールド | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `message_id` | `str` | 必須 | イベント由来の識別子 |
| `role` | `MessageRole` | 必須 | `user` または `assistant` |
| `content` | `str` | 必須 | 表示対象本文 |
| `timestamp` | `datetime | None` | 任意 | 発話時刻 |
| `format` | `MessageFormat` | 必須 | `plain_text` または `markdown` |
| `source_event_ids` | `list[str]` | 必須 | 生成元イベントの追跡用 |

### SessionMetadata

セッションに紐づく補助情報。

| フィールド | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `custom_title` | `str | None` | 任意 | メタデータ由来のタイトル |
| `first_user_message` | `str | None` | 任意 | タイトル補完候補 |
| `workspace_folder` | `str | None` | 任意 | ワークスペース情報 |
| `repository_path` | `str | None` | 任意 | リポジトリ情報 |
| `raw_sources` | `list[str]` | 必須 | どの入力ソースから採用したか |

### SessionSourceKind

セッションの主たる由来を表す列挙値。

* `transcript`
* `legacy_sqlite`

### MessageRole

発話者種別。

* `user`
* `assistant`

### MessageFormat

本文の表示形式。

* `plain_text`
* `markdown`

## UI 表示モデル

### SessionListItem

左ペイン一覧用の軽量モデル。

| フィールド | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `session_id` | `str` | 必須 | 一覧選択キー |
| `display_title` | `str` | 必須 | 一覧表示タイトル |
| `latest_timestamp` | `datetime | None` | 任意 | 最新順ソート用 |
| `oldest_timestamp` | `datetime | None` | 任意 | 古い順ソート用 |
| `message_count` | `int` | 必須 | 本文メッセージ数 |
| `has_warnings` | `bool` | 必須 | 問題あり表示用 |

### SessionDetailView

右ペインの表示単位。

| フィールド | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `session_id` | `str` | 必須 | 表示中セッション |
| `display_title` | `str` | 必須 | 詳細見出し |
| `messages` | `list[DisplayMessage]` | 必須 | 画面描画用メッセージ |
| `warnings` | `list[DisplayWarning]` | 必須 | 軽微な問題表示 |

### DisplayMessage

詳細表示用に整形済みのメッセージ。

| フィールド | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `role_label` | `str` | 必須 | `ユーザー` または `AI` |
| `content` | `str` | 必須 | 画面表示用本文 |
| `timestamp_text` | `str | None` | 任意 | 表示用に整形した時刻文字列 |
| `use_monospace` | `bool` | 必須 | 等幅フォント適用判定 |

### DisplayWarning

UI に通知する軽微な問題。

| フィールド | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `code` | `str` | 必須 | 識別用コード |
| `message` | `str` | 必須 | 表示文言 |

## エクスポートモデル

### MarkdownDocument

単一セッションを Markdown として出力するためのモデル。

| フィールド | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `session_id` | `str` | 必須 | 出力対象セッション |
| `title` | `str` | 必須 | 文書タイトル |
| `body` | `str` | 必須 | 完成済み Markdown 本文 |
| `suggested_filename` | `str` | 必須 | 保存ダイアログ初期値 |

### ExportBatch

複数エクスポート時の要求モデル。

| フィールド | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `session_ids` | `list[str]` | 必須 | 出力対象セッション群 |
| `output_directory` | `Path` | 必須 | 保存先ディレクトリ |

## 問題モデル

### ParseIssue

入力読取や復元時の問題を表す標準モデル。

| フィールド | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `severity` | `IssueSeverity` | 必須 | 問題の重大度 |
| `code` | `str` | 必須 | 機械可読な識別子 |
| `message` | `str` | 必須 | 人間向け説明 |
| `source_path` | `Path | None` | 任意 | 問題発生源 |
| `line_number` | `int | None` | 任意 | JSONL 行番号 |
| `session_id` | `str | None` | 任意 | 関連セッション |
| `is_skippable` | `bool` | 必須 | 処理継続可否 |

### IssueSeverity

* `info`
* `warning`
* `error`

## マッピング規則

### transcript JSONL から Session への変換

1. 先頭の `session.start` から `session_id` を確定する。
2. 既知イベントからユーザー発話とアシスタント発話を抽出する。
3. 本文化できない内部イベントは `Message` に変換しない。
4. 抽出した `Message` 群から `started_at`、`ended_at`、`latest_timestamp`、`oldest_timestamp` を計算する。
5. 補助メタデータがなければ、先頭ユーザー発話またはセッション ID を使ってタイトルを生成する。

### JSON メタデータのマージ

1. `session_id` 一致で対象 `Session` に紐づける。
2. `custom_title` が存在する場合のみタイトル候補として採用する。
3. 補助メタデータは本文とタイムスタンプを上書きしない。

### SQLite フォールバックの扱い

1. transcript が存在しない場合のみ、本文候補として採用を検討する。
2. transcript が存在する場合、SQLite は不足項目の補完専用とする。
3. GitHub Copilot Chat に紐づくキー空間であることを確認できないレコードは破棄する。

## 不変条件

* `Session.session_id` は空文字列を許可しない。
* transcript 由来の `Session` は、最低 1 件の `session.start` を持つ。
* `latest_timestamp` と `oldest_timestamp` は、存在する場合 `oldest_timestamp <= latest_timestamp` を満たす。
* `Message.role` は `user` または `assistant` のみとする。
* 元ファイルへの書き込みを行うモデルやメソッドは定義しない。

## Python 実装指針

* 正規化ドメインモデルは `dataclasses.dataclass` を基本とする。
* 時刻は内部表現として `datetime` を使い、UI 文字列化は表示層で行う。
* 入力モデルとドメインモデルは別型に分離し、同一クラスで兼用しない。
* `Path` は `pathlib.Path` を使用する。
* 既知イベントの判定は、`event_type` ごとの変換関数へ分離する。

## 最小実装順

1. `TranscriptEvent`、`TranscriptFile`、`ParseIssue` を実装する。
2. transcript JSONL から `Session` と `Message` を構築する。
3. 一覧表示用に `SessionListItem` を派生させる。
4. 詳細表示用に `SessionDetailView` を派生させる。
5. 単一セッションの `MarkdownDocument` 生成を実装する。
6. その後に JSON メタデータ統合、最後に SQLite フォールバックを追加する。