# ChatLogViewer

## テンプレートから作成後に実行する

以下箇所の名称をプロジェクト固有名詞に更新する

- workspaceのファイル名
- README.mdのタイトル
- pyproject.tomlのname

## Git セットアップ

チームで統一した Git 操作を行うためのセットアップスクリプトを用意している。
リポジトリをクローンしたら、最初に一度だけ実行すること。

### 実行方法

#### Windows の場合

`git-setup/setup-win.bat` をダブルクリックして実行する。

#### Mac の場合

ターミナルで以下を実行する。

```sh
./git-setup/setup-mac.sh
```

#### 環境反映の確認

以下コマンドにより`.gitattributes`の変更を既存ファイルに再適用する。

```powershell
git add --renormalize .
```

※ 履歴汚染リスクあるので利用には気を付けること

### ファイル構成

各ファイルの役割および構成は下記の通り。

```text
git-setup/
├── check-setup-win.bat   # Windows用Gitローカル設定が期待値どおりか確認するスクリプト
├── check-setup-mac.sh    # Mac用Gitローカル設定が期待値どおりか確認するスクリプト
├── COMMIT_TEMPLATE   # コミットメッセージのテンプレート
├── hooks/            # commit-msg などの共通Git hooksを管理するディレクトリ
├── setup-win.bat     # Windows用セットアップスクリプト
└── setup-mac.sh      # Mac用セットアップスクリプト
.gitattributes        # 改行コード・バイナリファイルの管理設定
```

### コミットメッセージについて

`git-setup/COMMIT_TEMPLATE`をテンプレートとして設定している。  
`git commit`時にエディタが開き、書き方の雛形が表示される。  

setup 実行時には `core.hooksPath` を `git-setup/hooks` に設定する。  
標準の hooks ディレクトリは通常参照されず、案内ファイル `SETUP_CREATED_core.hooksPath_changed.txt` が作成される。  
Git hooks を追加・変更する場合は `git-setup/hooks` を編集する。  

※ `-m` オプションを使用するとテンプレートは表示されない。
※ ユーザのコメントを上書することはしない。一度クリアしたり、何か入力されていたリするときは表示されない。

## Python専用環境の作成

### UVによる環境作成

pyproject.tomlの存在するフォルダ内で以下コマンドを実行することで作成済み環境と同期する

```powershell
uv sync
```

ライブラリ追加も同時に行う場合、後述の証明書エラーの対応が必要になるケースもある

### パッケージ追加

#### シンプルな追加手段

パッケージを追加する場合は以下

```powershell
uv add <パッケージ名>
```

バージョン指定が必要なら以下

```powershell
uv add "<パッケージ名>==<バージョン>"
```

#### 証明書エラーの対応

uvはMozillaの証明書を利用しているため、環境によってはエラーになる場合がある。
対策として`--native-tls`フラグと共にコマンドを実行する。

```powershell
uv add <パッケージ名> --native-tls
```

uv syncでエラーが生じる場合も同様である。

```powershell
uv sync --native-tls
```

#### ローカルパッケージの追加

ローカルのパッケージを直接追加する場合は、`pyproject.toml`に追記する。
追記後、内容を反映するために`uv sync`を実行する。

```text
[project]
dependencies = [
    # 相対パスまたは絶対パスで記述
    "package_name @ file:///path/to/package.whl",
]
```

#### requirementsから追加する場合

requirements.txtから追加するなら以下

```powershell
uv add -r requirements.txt
```

### パッケージ削除

パッケージを除外するなら以下

```powershell
uv remove <パッケージ名>
```
