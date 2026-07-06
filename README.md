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
| `--dictionary/-d` | 辞書モード(意味・発音・例文) |
| `--model/-m MODEL` | OpenAI モデル(デフォルト: `gpt-4o-mini`) |
| `--no-cache` | キャッシュを読まずに翻訳(結果は保存される) |
| `--clear-cache` | キャッシュを全削除して終了 |

言語未指定なら英日ペアとみなし、原文と逆の言語へ翻訳する。

```
yak hello                 # → こんにちは
yak -t フランス語 hello      # → bonjour
yak -d cat                # 辞書モード
echo "hello" | yak        # stdin から
yak                       # 対話モード
```

### 対話モード

引数なし・端末から起動すると対話モードになる。1 行ごとに翻訳する。

- `!指示` — セッション限定の追加システムプロンプトを追記
- `!` — 追加システムプロンプトをクリア
- Ctrl-D / Ctrl-C — 終了

### キャッシュ

翻訳・辞書結果は `platformdirs` の示すユーザーキャッシュディレクトリ
(Linux では `~/.cache/yak`)に diskcache で永続キャッシュされる
(上限 100MB、TTL なし)。同じ入力・言語・モデルの再実行は API を呼ばない。
