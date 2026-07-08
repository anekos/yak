# yak `--oneline / -1` フラグ設計

日付: 2026-07-08

## 目的

出力を 1 行に収める `--oneline / -1` フラグを追加する。grep やスクリプト、
エディタ組み込みなど、1 行の出力が欲しい用途向け。

## 要求

- `--oneline / -1` フラグを CLI に追加する。全モード共通。
- **辞書モード**: 通常の 意味/発音/例文 フォーマットの代わりに、
  **最初の意味だけ** を 1 行で出力する。
  - 例: `yak -1 cat` → `猫`
  - `meanings` が空の場合は空文字列を出力する(エラーにしない)。
- **翻訳モード**: 訳文の改行をスペース 1 個に置換して 1 行化する。
  空行(連続する改行)も 1 個のスペースに詰める。前後の空白は除去する。
  - 例: `今日はいい天気です。\n\n散歩に行きましょう。` →
    `今日はいい天気です。 散歩に行きましょう。`
- **対話モード**: フラグを `InteractiveSession` に伝播し、各行の応答に
  同じルールを適用する。`!` 行のフィードバック表示
  (`[system prompt 追加] …` など)は変更しない。
- モード自動判定(auto)との組み合わせは自由。判定結果のモードに応じて
  上記のどちらかのルールが適用される。

## 実装方針

表示側の純粋な後処理として実装する。API 呼び出し・プロンプト・
キャッシュキーには一切影響しない(同じ入力ならフラグの有無で
キャッシュを共有する)。

- `src/yak/render.py`
  - `render_dictionary(result, *, oneline: bool = False)` —
    oneline のとき `meanings[0]`(空なら `""`)を返す。
  - `oneline_text(text: str) -> str` — 改行(連続含む)をスペース 1 個に
    置換し、前後の空白を strip して返す。翻訳文用。
- `src/yak/interactive.py`
  - `InteractiveSession.__init__` に keyword-only の `oneline: bool = False`
    を追加。`handle_line` で辞書は `render_dictionary(..., oneline=...)`、
    翻訳は oneline のとき `oneline_text(...)` を通す。
- `src/yak/main.py`
  - `--oneline / -1` フラグ(`is_flag=True`)を追加し、one-shot 経路と
    対話モードの両方に伝播する。

## 却下した代替案

- **LLM に 1 行で出力させる**: プロンプトが分岐するためキャッシュキーが
  分かれ、同じ入力で API を 2 回呼ぶことになる。出力形式も不安定。却下。
- **辞書モードで全意味を「、」区切りで出力**: 検討したが「最初の意味だけ」
  を採用した(最短・代表的な意味のみ)。

## テスト

- `tests/test_render.py`: `render_dictionary(oneline=True)` が最初の意味
  だけを返す / meanings 空で `""` / `oneline_text` の改行・連続改行・
  前後空白の処理。
- `tests/test_cli.py`: `-1` 付き辞書モードで意味 1 つだけが出力される /
  `-1` 付き翻訳モードで複数行訳文が 1 行になる。
- `tests/test_interactive.py`: `oneline=True` のセッションで辞書・翻訳の
  両応答が 1 行になる / `!` 行のフィードバックは影響を受けない。
