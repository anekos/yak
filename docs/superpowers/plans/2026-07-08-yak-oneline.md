# yak `--oneline / -1` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 出力を 1 行に収める `--oneline / -1` フラグを追加する(辞書モードは最初の意味だけ、翻訳モードは改行をスペースに置換)。

**Architecture:** 表示側の純粋な後処理として実装する。API 呼び出し・プロンプト・キャッシュキーには一切影響しない。`render.py` に oneline ロジックを集約し、`InteractiveSession` と `main.py` の one-shot 経路の両方から使う。

**Tech Stack:** Python 3.13, click, pydantic, pytest(既存構成のまま。依存追加なし)

**Spec:** `docs/superpowers/specs/2026-07-08-yak-oneline-design.md`

## Global Constraints

- テスト実行は `uv run pytest`、静的検査は `make check`(mypy + ruff)。コミット前に両方通すこと。
- pre-commit フック(end-of-file-fixer 等)がファイルを修正してコミットが失敗することがある。その場合は `git add` し直して再コミットする。
- コミットメッセージ末尾に `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` を付ける。
- oneline は表示側の後処理であり、バックエンド呼び出し・キャッシュキーを変更してはならない。

---

### Task 1: render.py — oneline レンダリング

**Files:**
- Modify: `src/yak/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `yak.models.DictionaryResult`(既存)
- Produces:
  - `render_dictionary(result: DictionaryResult, *, oneline: bool = False) -> str` — oneline のとき最初の意味だけ(meanings 空なら `""`)を返す。デフォルトは従来どおり複数行フォーマット。
  - `oneline_text(text: str) -> str` — 改行(前後の空白・連続改行含む)をスペース 1 個に置換し、前後を strip して返す。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_render.py` の import を更新し、末尾にテストを追加:

```python
from yak.render import oneline_text, render_dictionary
```

```python
def test_render_dictionary_oneline_first_meaning() -> None:
    result = DictionaryResult(
        meanings=["猫", "ネコ科の動物"],
        pronunciation=Pronunciation(katakana="キャット", ipa="/kæt/"),
        examples=["I have a cat."],
    )
    assert render_dictionary(result, oneline=True) == "猫"


def test_render_dictionary_oneline_empty_meanings() -> None:
    result = DictionaryResult(
        meanings=[],
        pronunciation=Pronunciation(katakana="キャット", ipa="/kæt/"),
        examples=[],
    )
    assert render_dictionary(result, oneline=True) == ""


def test_oneline_text_joins_newlines() -> None:
    assert (
        oneline_text("今日はいい天気です。\n\n散歩に行きましょう。")
        == "今日はいい天気です。 散歩に行きましょう。"
    )


def test_oneline_text_strips_surrounding_whitespace() -> None:
    assert oneline_text("  hello \n world \n") == "hello world"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_render.py -v`
Expected: FAIL — `ImportError: cannot import name 'oneline_text'`

- [ ] **Step 3: 実装**

`src/yak/render.py` を以下の内容にする:

```python
import re

from yak.models import DictionaryResult


def render_dictionary(result: DictionaryResult, *, oneline: bool = False) -> str:
    if oneline:
        return result.meanings[0] if result.meanings else ""
    lines = ["意味:"]
    lines.extend(f"{i}. {meaning}" for i, meaning in enumerate(result.meanings, 1))
    lines.append("")
    lines.append("発音:")
    lines.append(f"{result.pronunciation.katakana} / {result.pronunciation.ipa}")
    lines.append("")
    lines.append("例文:")
    lines.extend(f"- {example}" for example in result.examples)
    return "\n".join(lines)


def oneline_text(text: str) -> str:
    return re.sub(r"\s*\n\s*", " ", text.strip())
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_render.py -v && make check`
Expected: 全テスト PASS、mypy / ruff エラーなし

- [ ] **Step 5: コミット**

```bash
git add src/yak/render.py tests/test_render.py
git commit -m "feat: add oneline rendering to render module

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: InteractiveSession — oneline 対応

**Files:**
- Modify: `src/yak/interactive.py`
- Test: `tests/test_interactive.py`

**Interfaces:**
- Consumes: `render_dictionary(result, *, oneline: bool = False)`、`oneline_text(text)`(Task 1)
- Produces: `InteractiveSession.__init__(backend, *, mode, classifier, from_lang, to_lang, oneline: bool = False)` — oneline のとき `handle_line` の応答が 1 行になる。`!` 行のフィードバックは影響を受けない。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_interactive.py`。`_session` ヘルパーに `oneline` パラメータを追加:

```python
def _session(
    backend: FakeBackend,
    mode: Mode = "translation",
    classifier: ModeClassifier | None = None,
    oneline: bool = False,
) -> InteractiveSession:
    return InteractiveSession(
        backend,  # type: ignore[arg-type]
        mode=mode,
        classifier=classifier,
        from_lang=None,
        to_lang=None,
        oneline=oneline,
    )
```

複数行の訳文を返すバックエンドと oneline テストを追加(import に `DictionaryResult`, `Pronunciation` を追加: `from yak.models import DictionaryResult, Pronunciation, TranslationResult`):

```python
class MultilineBackend:
    """複数行の結果を返す、oneline テスト用バックエンド。"""

    def translate(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> TranslationResult:
        return TranslationResult(
            detected_source_language="English",
            translated_text="一行目。\n\n二行目。",
        )

    def lookup(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> DictionaryResult:
        return DictionaryResult(
            meanings=["猫", "ネコ科の動物"],
            pronunciation=Pronunciation(katakana="キャット", ipa="/kæt/"),
            examples=["I have a cat."],
        )


def test_oneline_translation_joins_lines() -> None:
    session = InteractiveSession(
        MultilineBackend(),  # type: ignore[arg-type]
        mode="translation",
        classifier=None,
        from_lang=None,
        to_lang=None,
        oneline=True,
    )
    assert session.handle_line("hello") == "一行目。 二行目。"


def test_oneline_dictionary_first_meaning_only() -> None:
    session = InteractiveSession(
        MultilineBackend(),  # type: ignore[arg-type]
        mode="dictionary",
        classifier=None,
        from_lang=None,
        to_lang=None,
        oneline=True,
    )
    assert session.handle_line("cat") == "猫"


def test_oneline_does_not_affect_bang_feedback() -> None:
    session = _session(FakeBackend(), oneline=True)
    feedback = session.handle_line("!Use polite form.")
    assert feedback == "[system prompt 追加] Use polite form."
    assert session.handle_line("!") == "[system prompt をクリアしました]"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_interactive.py -v`
Expected: FAIL — `TypeError: InteractiveSession.__init__() got an unexpected keyword argument 'oneline'`

- [ ] **Step 3: 実装**

`src/yak/interactive.py` を修正。import に `oneline_text` を追加:

```python
from yak.render import oneline_text, render_dictionary
```

`__init__` に keyword-only 引数を追加:

```python
    def __init__(
        self,
        backend: Translator | DictionaryProvider,
        *,
        mode: Mode,
        classifier: ModeClassifier | None,
        from_lang: str | None,
        to_lang: str | None,
        oneline: bool = False,
    ) -> None:
        self._backend = backend
        self._mode = mode
        self._classifier = classifier
        self._from_lang = from_lang
        self._to_lang = to_lang
        self._oneline = oneline
        self._instructions: list[str] = []
```

`handle_line` の後半を修正:

```python
        extra = "\n".join(self._instructions) if self._instructions else None
        if self._use_dictionary(line):
            if not isinstance(self._backend, DictionaryProvider):
                raise YakError("this backend does not support dictionary mode")
            return render_dictionary(
                self._backend.lookup(line, self._from_lang, self._to_lang, extra),
                oneline=self._oneline,
            )
        if not isinstance(self._backend, Translator):
            raise YakError("this backend does not support translation mode")
        translated = self._backend.translate(
            line, self._from_lang, self._to_lang, extra
        ).translated_text
        return oneline_text(translated) if self._oneline else translated
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_interactive.py -v && make check`
Expected: 全テスト PASS、mypy / ruff エラーなし

- [ ] **Step 5: コミット**

```bash
git add src/yak/interactive.py tests/test_interactive.py
git commit -m "feat: support oneline output in interactive session

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: CLI フラグ `--oneline / -1` と README

**Files:**
- Modify: `src/yak/main.py`
- Modify: `README.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `render_dictionary(result, *, oneline)`、`oneline_text(text)`(Task 1)、`InteractiveSession(..., oneline=...)`(Task 2)
- Produces: CLI フラグ `--oneline / -1`(is_flag)。one-shot 経路と対話モードの両方に適用される。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_cli.py` の末尾に追加(import に `TranslationResult` は既にある):

```python
def test_oneline_dictionary_outputs_first_meaning(
    fake_backend: FakeBackend,
) -> None:
    result = CliRunner().invoke(main, ["-d", "-1", "cat"])
    assert result.exit_code == 0
    assert result.output == "猫\n"


def test_oneline_translation_joins_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    class MultilineBackend(FakeBackend):
        def translate(
            self,
            text: str,
            from_lang: str | None,
            to_lang: str | None,
            extra_instruction: str | None,
        ) -> TranslationResult:
            super().translate(text, from_lang, to_lang, extra_instruction)
            return TranslationResult(
                detected_source_language="English",
                translated_text="一行目。\n\n二行目。",
            )

    _patch_factories(monkeypatch, MultilineBackend(), FakeClassifier())
    result = CliRunner().invoke(main, ["--translator", "--oneline", "hello"])
    assert result.exit_code == 0
    assert result.output == "一行目。 二行目。\n"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_cli.py -v`
Expected: 新規 2 テストが FAIL — click が `-1` / `--oneline` を "No such option" として exit_code 2 を返す

- [ ] **Step 3: 実装**

`src/yak/main.py` を修正。import に `oneline_text` を追加:

```python
from yak.render import oneline_text, render_dictionary
```

`--clear-cache` オプションの直後(`@click.argument` の前)にオプションを追加:

```python
@click.option(
    "--oneline", "-1", "oneline", is_flag=True, help="Output a single line"
)
```

`main` のシグネチャに `oneline: bool` を追加(`clear_cache_flag` の後、`text` の前):

```python
def main(
    from_lang: str | None,
    to_lang: str | None,
    dictionary: bool,
    translator: bool,
    model: str,
    classifier_model: str,
    no_cache: bool,
    clear_cache_flag: bool,
    oneline: bool,
    text: str | None,
) -> None:
```

対話モード起動の `InteractiveSession(...)` に `oneline=oneline,` を追加:

```python
                run_interactive(
                    InteractiveSession(
                        backend,
                        mode=mode,
                        classifier=classifier,
                        from_lang=from_lang,
                        to_lang=to_lang,
                        oneline=oneline,
                    )
                )
```

one-shot 経路の出力部分を修正:

```python
        if use_dictionary:
            if not isinstance(backend, DictionaryProvider):
                raise YakError("this backend does not support dictionary mode")
            click.echo(
                render_dictionary(
                    backend.lookup(text, from_lang, to_lang, None),
                    oneline=oneline,
                )
            )
        else:
            translated = backend.translate(
                text, from_lang, to_lang, None
            ).translated_text
            click.echo(oneline_text(translated) if oneline else translated)
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest && make check`
Expected: 全テスト PASS、mypy / ruff エラーなし

- [ ] **Step 5: README 更新**

`README.md` のオプション表、`--clear-cache` 行の後に追加:

```markdown
| `--oneline/-1` | 出力を 1 行にする(辞書モードは最初の意味のみ、翻訳モードは改行をスペースに置換) |
```

使用例ブロックに 1 行追加(`yak -d cat` の行の後):

```
yak -1 cat                # → 猫 (1 行出力)
```

- [ ] **Step 6: コミット**

```bash
git add src/yak/main.py tests/test_cli.py README.md
git commit -m "feat: add --oneline/-1 flag for single-line output

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
