# yak — 翻訳 CLI 設計書

日付: 2026-07-06
状態: 承認済み

## 概要

yak は OpenAI API を使った翻訳 CLI ツール。通常モード(訳文のみ出力)と
dictionary モード(意味・発音・例文を辞書形式で出力)を持つ。
将来 Google 翻訳などの別バックエンドへ切り替えられるよう、
バックエンドを Protocol で抽象化する。

## コマンド仕様

```
yak [OPTIONS] [TEXT]
```

| オプション | 説明 |
|---|---|
| `--from/-f LANG` | 原文の言語 |
| `--to/-t LANG` | 訳先の言語 |
| `--dictionary/-d` | 辞書モード |
| `--model/-m MODEL` | OpenAI モデル(デフォルト: `gpt-4o-mini`) |

### 言語決定ルール(両モード共通)

- `--from`/`--to` とも未指定 → 英日ペアとみなし、原文の言語を判定して逆の言語へ翻訳
- `--to` のみ指定 → 原文言語は自動判定、指定言語へ翻訳
- `--from` のみ指定 → 英日ペアの逆側へ翻訳(from が英日以外なら日本語へ)
- 言語名は自由記述(`en`, `English`, `フランス語` など)をそのままプロンプトへ渡し、
  LLM に解釈させる

### 入力の決定

1. `TEXT` 引数あり → それを処理して終了
2. `TEXT` なし & stdin がパイプ → stdin 全体を読んで処理して終了
3. `TEXT` なし & stdin が端末 → 対話モード

### 対話モード

- 1 行入力するごとに翻訳(または辞書引き)して結果を表示
- `!text` → text をセッション限定の追加システムプロンプトとして**追記**(累積)。
  追記時はその旨をフィードバック表示する(例: `[system prompt 追加] …`)
- `!` のみの行 → 追加システムプロンプトを全クリア。
  クリア時もフィードバック表示する(例: `[system prompt をクリアしました]`)
- Ctrl-D / Ctrl-C で終了
- `--from/--to/--dictionary` は対話モード中の全リクエストに適用

### エラー処理

- 環境変数 `OPENAI_API_KEY_FOR_YAK` 未設定 → stderr にメッセージ、exit 1
- API エラー → stderr に簡潔なメッセージ、exit 1(対話モード中はセッション継続)
- 非 LLM バックエンド(将来の Google 翻訳など)で辞書モードを指定
  → 非対応である旨をエラー表示

## アーキテクチャ

```
src/yak/
├── main.py          # click CLI エントリポイント(引数解釈、モード分岐のみ)
├── models.py        # Pydantic モデル = JSON スキーマ定義
├── backends/
│   ├── base.py      # Protocol 定義 (Translator / DictionaryProvider)
│   └── openai.py    # OpenAI 実装(両プロトコルを実装)
├── render.py        # DictionaryResult → 辞書フォーマット整形
└── interactive.py   # 対話モード (REPL)
```

- 依存追加: `openai`, `pydantic`
- CLI 層は Protocol にのみ依存する。バックエンド生成は `main.py` 内の
  ファクトリ関数 1 つに集約し、将来 `--backend google` を追加する際は
  ファクトリと `backends/google.py` の追加だけで済むようにする
- API キーは `OPENAI_API_KEY_FOR_YAK` から取得する

### Protocol 定義

```python
class Translator(Protocol):
    def translate(
        self, text: str, from_lang: str | None, to_lang: str | None,
        extra_instruction: str | None,
    ) -> TranslationResult: ...

class DictionaryProvider(Protocol):
    def lookup(
        self, text: str, from_lang: str | None, to_lang: str | None,
        extra_instruction: str | None,
    ) -> DictionaryResult: ...
```

Google 翻訳のような非 LLM バックエンドは `Translator` のみ実装する。

### データフロー

CLI が引数解釈 → ファクトリでバックエンド生成 → `translate()` / `lookup()` 呼び出し
→ Pydantic モデル受領 → 通常モードは `translated_text` をそのまま print、
辞書モードは `render.py` で整形して print。

## JSON スキーマ(Pydantic モデル)

```python
class TranslationResult(BaseModel):
    detected_source_language: str   # 判定した原文言語
    translated_text: str

class Pronunciation(BaseModel):
    katakana: str                   # カタカナ読み
    ipa: str                        # 発音記号

class DictionaryResult(BaseModel):
    meanings: list[str]             # 意味(複数)
    pronunciation: Pronunciation    # 訳語の発音
    examples: list[str]             # 例文
```

OpenAI SDK の Structured Outputs(`.parse()`)に Pydantic モデルを渡し、
常に同じ構造で受け取る。

## 出力フォーマット

### 通常モード

訳文のみを標準出力に出す(パイプ処理しやすい UNIX 的挙動)。

### 辞書モード

```
意味:
1. 猫
2. (俗) ねこ、キャット

発音:
キャット / /kæt/

例文:
- The cat sat on the mat.
- ...
```

- 発音は常に「訳語側」の発音を表示する
  (例: `yak -d 猫` → cat の発音 `キャット / /kæt/`)
- 訳先が日本語以外でもフォーマットは同一。カタカナ読みはそのまま出す

## テスト方針

pytest を使用し、実 API は呼ばない。

- `render.py`: `DictionaryResult` → テキスト整形の検証
- 言語決定ルール: from/to の組み合わせごとの解決結果
- CLI: click の `CliRunner` + フェイク `Translator`/`DictionaryProvider` を注入し、
  通常/辞書/引数エラーの動作を確認
- 対話モードの `!` 処理: prefix 解釈とセッション状態のユニットテスト

## ドキュメント

README にインストール方法(`make install`)、環境変数、使用例を記載する。
