# yak

OpenAI API を使った翻訳 CLI。

## インストール

```
make setup    # 開発環境
make install  # uv tool としてインストール
```

## 設定

環境変数 `OPENAI_API_KEY_FOR_YAK` に OpenAI API キーを設定する。

## 使い方

```
yak [OPTIONS] [TEXT]
```

| オプション | 説明 |
|---|---|
| `--from/-f LANG` | 原文の言語 |
| `--to/-t LANG` | 訳先の言語 |
| `--dictionary/-d` | 辞書モードを強制(意味・発音・例文) |
| `--translator` | 翻訳モードを強制 |
| `--model/-m MODEL` | 翻訳・辞書用モデル(envvar: `YAK_MODEL`、デフォルト: `gpt-5-mini`) |
| `--classifier-model MODEL` | モード自動判定用モデル(envvar: `YAK_CLASSIFIER_MODEL`、デフォルト: `gpt-5-nano`) |
| `--reasoning-effort/-r EFFORT` | 推論の深さ(envvar: `YAK_REASONING_EFFORT`、デフォルト: `minimal`) |
| `--no-cache` | キャッシュを読まずに翻訳(結果は保存される) |
| `--clear-cache` | キャッシュを全削除して終了 |
| `--oneline/-1` | 出力を 1 行にする(辞書モードは最初の意味のみ、翻訳モードは改行をスペースに置換) |

言語未指定なら英日ペアとみなし、原文と逆の言語へ翻訳する。

`--reasoning-effort` は gpt-5 系の推論量を制御する。深いほど訳文の質は上がるが
遅くなる。指定できる値は `none` / `minimal` / `low` / `medium` / `high` / `xhigh`
(どれを受け付けるかはモデル依存で、`none` と `xhigh` は gpt-5.1 系のみ)。
翻訳・辞書用モデルとモード自動判定用モデルの両方に適用される。
API のデフォルトは `medium` だが、yak は速度優先で `minimal` を既定にしている。

モード未指定の場合は入力を軽量モデルで判定し、単語・熟語・慣用句などの
「辞書の見出し語」なら辞書モード、文なら翻訳モードで処理する
(この自動判定は追加の API 呼び出しを 1 回行う。判定結果もキャッシュされる)。

```
yak hello                 # → こんにちは
yak -t フランス語 hello      # → bonjour
yak -d cat                # 辞書モード
yak -1 cat                # → 猫 (1 行出力)
echo "hello" | yak        # stdin から
yak                       # 対話モード
```

### 対話モード

引数なし・端末から起動すると対話モードになる。1 行ごとに翻訳する。

- `!指示` — セッション限定の追加システムプロンプトを追記
- `!` — 追加システムプロンプトをクリア
- Ctrl-D / Ctrl-C — 終了

readline による行編集が使える。Ctrl-P / Ctrl-N で履歴を辿り、Ctrl-R で履歴を検索、
Ctrl-A / Ctrl-E で行頭・行末へ移動する。入力履歴は
`platformdirs` の示すユーザー状態ディレクトリ(Linux では `~/.local/state/yak/history`)に
最大 1000 行、パーミッション 600 で保存され、次回以降のセッションでも辿れる。

### キャッシュ

翻訳・辞書・モード判定の結果は `platformdirs` の示すユーザーキャッシュディレクトリ
(Linux では `~/.cache/yak`)に diskcache で永続キャッシュされる
(上限 100MB、TTL なし)。同じ入力・言語・モデル・推論の深さの再実行は API を呼ばない。
