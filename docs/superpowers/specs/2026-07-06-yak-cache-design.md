# yak — 翻訳結果キャッシュ設計書

日付: 2026-07-06
状態: 承認済み
前提: `docs/superpowers/specs/2026-07-06-yak-translation-cli-design.md`

## 概要

同じ入力に対する API 呼び出しを避けるため、diskcache + platformdirs で
翻訳・辞書結果を永続キャッシュする。キャッシュは任意のバックエンドを包む
ラッパー(`CachingBackend`)として実装し、既存の Protocol 設計に乗せる。

## アーキテクチャ

新モジュール `src/yak/cache.py`(依存追加: `diskcache`, `platformdirs`)

```python
def cache_directory() -> Path: ...
    # platformdirs.user_cache_dir("yak")(例: ~/.cache/yak)

def open_cache() -> diskcache.Cache: ...
    # Cache(cache_directory(), size_limit=100MB)

class CachingBackend:
    """Translator / DictionaryProvider 両プロトコルを実装するラッパー。"""

    def __init__(
        self,
        inner: Translator | DictionaryProvider,
        cache: diskcache.Cache,
        *,
        namespace: str,
        read_enabled: bool = True,
    ) -> None: ...
```

- `translate()` / `lookup()` はキーを組み立て、ヒットすれば inner を呼ばずに
  返す。ミス時は inner を呼んで結果を保存する
- CachingBackend 自体は両プロトコルのメソッドを持つため、CLI /
  InteractiveSession の isinstance ガードはラッパーに対して常に通る。
  そのため inner が対象プロトコルを実装していない場合の検出は
  CachingBackend 側で行い、既存と同一メッセージの YakError を送出する
- ファクトリ(`main.create_backend`)が
  `CachingBackend(OpenAIBackend(...), open_cache(), namespace=f"openai:{model}")`
  と包む。OpenAIBackend と interactive.py は無変更

### キャッシュキー

タプル: `("translate" | "lookup", namespace, text, from_lang, to_lang, extra_instruction)`

- `namespace` はファクトリが渡す文字列(現状 `f"openai:{model}"`)。
  モデルを変えれば別キャッシュになり、将来のバックエンド(例 `"google"`)とも
  衝突しない
- 対話モードの `!` 追加指示は `extra_instruction` としてキーに含まれるため、
  指示が違えば別エントリになる

### キャッシュ値

Pydantic モデルを `model_dump()` した dict で保存し、取得時に
`model_validate()` で復元する(pickle でクラス定義に依存させない)。

### 寿命

TTL なし(翻訳結果は陳腐化しない)。サイズ上限 100MB を超えた分は
diskcache の LRU 系退避に任せる。

## CLI

| 追加オプション | 挙動 |
|---|---|
| `--no-cache` | キャッシュを読まずに API を呼ぶ。結果は保存する(`read_enabled=False`) |
| `--clear-cache` | キャッシュを全削除して終了(TEXT 不要、API キー不要)。`キャッシュをクリアしました (N 件)` を表示して exit 0 |

- `--clear-cache` は入力・バックエンド生成より先に判定する
- 通常の翻訳・辞書・対話モードはすべて自動的にキャッシュ経由となる
  (観測できる挙動の変化はレイテンシのみ)

## エラー処理

- キャッシュディレクトリは `diskcache.Cache` が自動作成する
- キャッシュ層で特別なエラーハンドリングはしない(diskcache は破損時も
  自己修復的に動作する。YAGNI)

## テスト方針

実 API は呼ばない。`tmp_path` に実 diskcache を作ってテストする。

- `CachingBackend`: 同一引数の 2 回目の呼び出しで inner が呼ばれず、
  1 回目と同じ結果が返る
- キー分離: モード(translate/lookup)、言語、extra_instruction、namespace の
  いずれかが違えば別エントリ
- `read_enabled=False`: inner が毎回呼ばれるが書き込みはされる
  (その後 `read_enabled=True` でヒットすることを確認)
- CLI: `--no-cache` が `read_enabled=False` としてファクトリに伝わる。
  `--clear-cache` がクリアして exit 0(キャッシュディレクトリは
  monkeypatch で tmp_path に向ける)
