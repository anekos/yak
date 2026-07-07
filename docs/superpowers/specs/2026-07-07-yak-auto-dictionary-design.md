# yak — 自動辞書モード設計書

日付: 2026-07-07
状態: 承認済み
前提: `docs/superpowers/specs/2026-07-06-yak-translation-cli-design.md`、
`docs/superpowers/specs/2026-07-06-yak-cache-design.md`

## 概要

モード指定がない場合、入力が「辞書の見出し語」かどうかを軽量 LLM で自動判定し、
見出し語なら辞書モード、文なら翻訳モードで処理する。`--translator` フラグで
翻訳モードを強制できる(既存の `--dictionary/-d` は辞書モードの強制)。
あわせて、モデル指定を「CLI オプション > 環境変数 > デフォルト」の 3 段階にする。

## モード解決ルール

引数・stdin パイプ・対話モードの各行、すべてに共通:

1. `--dictionary/-d` → 辞書モード(分類コールなし)
2. `--translator` → 翻訳モード(分類コールなし)
3. 両方指定 → エラー `cannot use --dictionary and --translator together`
   (YakError → stderr、exit 1)
4. どちらもなし → 自動判定: 分類モデルに「これは辞書の見出し語か?」を
   Structured Output(bool)で判定させる
   - 見出し語 = 単語、または辞書に載る短い定型句(熟語・句動詞・慣用句・複合語。
     例: `look up`, `in spite of`, `猫`, `摩訶不思議`)。言語は問わない
   - 文・自由テキストなら翻訳モード

## モデル解決

両モデルとも「CLI オプション > 環境変数 > デフォルト」で解決する
(click の `envvar` サポートを使用)。

| 用途 | オプション | 環境変数 | デフォルト |
|---|---|---|---|
| 翻訳・辞書 | `--model/-m` | `YAK_MODEL` | `gpt-5-mini` |
| モード自動判定 | `--classifier-model` | `YAK_CLASSIFIER_MODEL` | `gpt-5-nano` |

- 翻訳は品質のためミドルレンジ、分類は bool 判定のみなので最軽量にする
- 既存デフォルト `gpt-4o-mini` は `gpt-5-mini` に変更する
  (キャッシュ namespace にモデル名が含まれるため、旧エントリは無害に残るだけ)

## アーキテクチャ

既存パターンの延長。新モジュールは追加しない。

```python
# models.py に追加
class ModeDecision(BaseModel):
    is_dictionary_entry: bool

# backends/base.py に追加
@runtime_checkable
class ModeClassifier(Protocol):
    def classify(self, text: str) -> ModeDecision: ...
```

- `OpenAIBackend.classify()` を追加。既存の `_parse` を再利用し、
  分類システムプロンプト + `ModeDecision` スキーマで判定する
- ファクトリ(`main.py`)が分類専用の `OpenAIBackend`(モデル = 分類モデル)を
  もう 1 つ作り、`CachingBackend` で包む
- `CachingBackend.classify()` を追加。キーは
  `("classify", namespace, text, None, None, None)`(既存の 6 要素タプル形状を
  維持)。namespace は `f"openai:{classifier_model}"`。
  分類結果もキャッシュされるため、同一入力の再実行は API コール完全ゼロ
- inner が `ModeClassifier` を実装しない場合は
  `YakError("this backend does not support mode classification")` を送出する
  (既存の translation/dictionary ガードと同じパターン)
- `InteractiveSession` は `dictionary: bool` の代わりにモード
  (`"dictionary" | "translation" | "auto"`)と classifier を受け取り、
  行ごとにモードを解決する。`!` 行(システムプロンプト操作)は分類しない

## エラー処理

- 分類コールの API エラーも既存どおり `YakError` → stderr + exit 1
  (対話モードでは行単位でエラー表示しセッション継続)

## テスト方針

実 API は呼ばない。

- `OpenAIBackend.classify`: フェイククライアントで
  `response_format is ModeDecision` とメッセージ構造を検証
- `CachingBackend.classify`: 同一入力の 2 回目で inner が呼ばれない
- CLI(フェイク classifier / backend 注入):
  - 自動判定: classifier が True → 辞書フォーマット出力、False → 訳文のみ
  - `-d` / `--translator` 指定時は classifier が呼ばれない
  - 併用はエラー(exit 1、メッセージ確認)
  - モデル解決: envvar とオプションの優先順位(オプション > envvar)
- `InteractiveSession`: auto モードで行ごとに分類が呼ばれる、
  `!` 行では呼ばれない
- README: `--translator`、`--classifier-model`、環境変数、
  自動判定の説明を追記
