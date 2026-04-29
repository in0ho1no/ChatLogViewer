---
applyTo: "src/**/*.py"
description: "Python ファイルを編集・作成・レビューするときに使う。uv、型ヒント、pathlib、pyproject 準拠の補足ルール。"
---

- コーディング規約の正本は pyproject.toml とし、競合時はそちらを優先する
- Python の実行や検証は uv run を使う
- パッケージ追加は勝手に行わず、必要時はユーザー確認のうえ uv add を使う
- ファイルパスの操作は os.path ではなく pathlib.Path を使う
- 必要な変数や関数には型ヒントを付ける
