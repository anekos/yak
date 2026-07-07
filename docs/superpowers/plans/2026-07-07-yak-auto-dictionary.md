# yak 自動辞書モード Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** モード未指定時に軽量 LLM で「辞書の見出し語か」を判定して辞書/翻訳を自動選択し、`--translator` フラグと 3 段階のモデル解決(オプション > 環境変数 > デフォルト)を追加する。

**Architecture:** `ModeClassifier` Protocol と `ModeDecision` スキーマを追加し、`OpenAIBackend.classify()`(既存 `_parse` を再利用)と `CachingBackend.classify()`(分類結果もキャッシュ)を実装。CLI と `InteractiveSession` はモード(`dictionary | translation | auto`)を解決してディスパッチする。

**Tech Stack:** 既存スタックのみ(click の `envvar` サポートを使用。依存追加なし)

**Spec:** `docs/superpowers/specs/2026-07-07-yak-auto-dictionary-design.md`

## Global Constraints

- モード解決(引数・stdin・対話モード各行すべて共通):
  `-d` → 辞書 / `--translator` → 翻訳 / 併用 →
  `YakError("cannot use --dictionary and --translator together")` / どちらもなし → 自動判定
- モデル解決は「CLI オプション > 環境変数 > デフォルト」:
  翻訳・辞書 = `--model/-m` / `YAK_MODEL` / `gpt-5-mini`、
  分類 = `--classifier-model` / `YAK_CLASSIFIER_MODEL` / `gpt-5-nano`
- 分類キャッシュキー: `("classify", namespace, text, None, None, None)`、
  namespace は `f"openai:{classifier_model}"`
- 分類非対応 inner のエラー: `YakError("this backend does not support mode classification")`
- 対話モードの `!` 行(システムプロンプト操作)は分類しない
- 各タスク完了時に `make check`(mypy + ruff)が通ること
- コミット時は pre-commit フックが走る。フックがファイルを修正してコミットが
  失敗したら、`git add` し直して再コミットする

---

### Task 1: ModeDecision / ModeClassifier / OpenAIBackend.classify

**Files:**
- Modify: `src/yak/models.py`(ModeDecision 追加)
- Modify: `src/yak/backends/base.py`(ModeClassifier Protocol 追加)
- Modify: `src/yak/backends/openai.py`(classify 追加、デフォルトモデル定数変更)
- Test: `tests/test_openai_backend.py`(テスト追記)

**Interfaces:**
- Consumes: `OpenAIBackend._parse`(既存の Structured Output ヘルパー)
- Produces: `yak.models.ModeDecision(is_dictionary_entry: bool)`
- Produces: `yak.backends.base.ModeClassifier` Protocol — `classify(text: str) -> ModeDecision`
- Produces: `yak.backends.openai.OpenAIBackend.classify(text: str) -> ModeDecision`
- Produces: `yak.backends.openai.DEFAULT_MODEL = "gpt-5-mini"`(変更)、
  `yak.backends.openai.DEFAULT_CLASSIFIER_MODEL = "gpt-5-nano"`(新規)

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_openai_backend.py` の import に `ModeDecision` を追加:

```python
from yak.models import DictionaryResult, ModeDecision, Pronunciation, TranslationResult
```

`DEFAULT_MODEL` の import 行に `DEFAULT_CLASSIFIER_MODEL` も追加し
(現在 `DEFAULT_MODEL` を import していない場合は新たに追加)、ファイル末尾にテストを追記:

```python
def test_default_models() -> None:
    assert DEFAULT_MODEL == "gpt-5-mini"
    assert DEFAULT_CLASSIFIER_MODEL == "gpt-5-nano"


def test_classify_returns_parsed_result() -> None:
    expected = ModeDecision(is_dictionary_entry=True)
    backend, fake = _backend(expected)
    result = backend.classify("cat")
    assert result == expected
    call = fake.calls[0]
    assert call["model"] == "test-model"
    assert call["response_format"] is ModeDecision
    assert call["messages"][1] == {"role": "user", "content": "cat"}
```

import 文の例(既存の import と統合すること):

```python
from yak.backends.openai import (
    DEFAULT_CLASSIFIER_MODEL,
    DEFAULT_MODEL,
    OpenAIBackend,
    language_instruction,
)
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run pytest tests/test_openai_backend.py -v`
Expected: FAIL(`ImportError: cannot import name 'DEFAULT_CLASSIFIER_MODEL'`)

- [ ] **Step 3: models.py に ModeDecision を追加する**

`src/yak/models.py` の末尾に追記:

```python
class ModeDecision(BaseModel):
    """モード自動判定の結果。OpenAI Structured Outputs のスキーマとしても使う。"""

    is_dictionary_entry: bool
```

- [ ] **Step 4: base.py に ModeClassifier を追加する**

`src/yak/backends/base.py` の import を更新:

```python
from yak.models import DictionaryResult, ModeDecision, TranslationResult
```

末尾に追記:

```python
@runtime_checkable
class ModeClassifier(Protocol):
    """入力が辞書の見出し語かどうかを判定するバックエンドのインターフェイス。"""

    def classify(self, text: str) -> ModeDecision: ...
```

- [ ] **Step 5: openai.py に classify を追加する**

`src/yak/backends/openai.py` を修正する。

定数を変更・追加(`DEFAULT_MODEL = "gpt-4o-mini"` を置き換え):

```python
DEFAULT_MODEL = "gpt-5-mini"
DEFAULT_CLASSIFIER_MODEL = "gpt-5-nano"
```

import に `ModeDecision` を追加:

```python
from yak.models import DictionaryResult, ModeDecision, TranslationResult
```

システムプロンプト定数を追加(`_DICTIONARY_SYSTEM` の後):

```python
_CLASSIFY_SYSTEM = (
    "You are a mode classifier for a translation tool. "
    "Decide whether the input is a dictionary headword: a single word, or a "
    "short set phrase that belongs in a dictionary as an entry, such as an "
    "idiom, phrasal verb, or compound (e.g. 'look up', 'in spite of', '猫'). "
    "Sentences and free-form text are not dictionary headwords. "
    "The input may be in any language."
)
```

`OpenAIBackend` に `lookup` の後、`_parse` の前にメソッドを追加:

```python
    def classify(self, text: str) -> ModeDecision:
        return self._parse(_CLASSIFY_SYSTEM, text, None, ModeDecision)
```

- [ ] **Step 6: テストが通ることを確認する**

Run: `uv run pytest tests/test_openai_backend.py -v`
Expected: PASS(11 passed)

Run: `uv run pytest`
Expected: 全テスト PASS(43)

Run: `make check`
Expected: エラーなし

- [ ] **Step 7: コミット**

```bash
git add src/yak/models.py src/yak/backends/base.py src/yak/backends/openai.py \
        tests/test_openai_backend.py
git commit -m "feat: add mode classification to OpenAI backend"
```

---

### Task 2: CachingBackend.classify と FakeClassifier

**Files:**
- Modify: `src/yak/cache.py`(classify 追加、inner の型を拡張)
- Modify: `tests/test_cli.py`(FakeClassifier クラス追加のみ — CLI テスト変更は Task 3)
- Test: `tests/test_cache.py`(テスト追記)

**Interfaces:**
- Consumes: `ModeClassifier` / `ModeDecision`(Task 1)
- Produces: `yak.cache.CachingBackend.classify(text: str) -> ModeDecision`
  (キー `("classify", namespace, text, None, None, None)`、read_enabled/write の
  挙動は translate/lookup と同一)
- Produces: `tests.test_cli.FakeClassifier` —
  `FakeClassifier(is_dictionary_entry: bool = False)`、
  属性 `decision: bool`(後から変更可)と `classify_calls: list[str]`

- [ ] **Step 1: FakeClassifier を追加する**

`tests/test_cli.py` の import に `ModeDecision` を追加し、`FakeBackend` クラスの
直後に追記:

```python
class FakeClassifier:
    def __init__(self, is_dictionary_entry: bool = False) -> None:
        self.decision = is_dictionary_entry
        self.classify_calls: list[str] = []

    def classify(self, text: str) -> ModeDecision:
        self.classify_calls.append(text)
        return ModeDecision(is_dictionary_entry=self.decision)
```

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_cache.py` の import に `FakeClassifier` を追加
(`from tests.test_cli import FakeBackend, FakeClassifier`)し、末尾に追記:

```python
def test_second_classify_hits_cache(tmp_path: Path) -> None:
    classifier = FakeClassifier(is_dictionary_entry=True)
    caching = CachingBackend(classifier, _make_cache(tmp_path), namespace="test")
    first = caching.classify("cat")
    second = caching.classify("cat")
    assert first == second
    assert first.is_dictionary_entry is True
    assert classifier.classify_calls == ["cat"]


def test_classify_with_translate_only_inner_raises(tmp_path: Path) -> None:
    caching = CachingBackend(
        TranslateOnlyBackend(), _make_cache(tmp_path), namespace="test"
    )
    with pytest.raises(YakError, match="mode classification"):
        caching.classify("cat")
```

- [ ] **Step 3: テストが失敗することを確認する**

Run: `uv run pytest tests/test_cache.py -v`
Expected: FAIL(`AttributeError: 'CachingBackend' object has no attribute 'classify'`)

- [ ] **Step 4: cache.py に classify を実装する**

`src/yak/cache.py` の import を更新:

```python
from yak.backends.base import DictionaryProvider, ModeClassifier, Translator
from yak.models import DictionaryResult, ModeDecision, TranslationResult
```

`CachingBackend.__init__` の inner の型注釈を拡張:

```python
        inner: Translator | DictionaryProvider | ModeClassifier,
```

`lookup` の後にメソッドを追加:

```python
    def classify(self, text: str) -> ModeDecision:
        key = ("classify", self._namespace, text, None, None, None)
        if self._read_enabled:
            cached = self._cache.get(key)
            if cached is not None:
                return ModeDecision.model_validate(cached)
        if not isinstance(self._inner, ModeClassifier):
            raise YakError("this backend does not support mode classification")
        result = self._inner.classify(text)
        self._cache[key] = result.model_dump()
        return result
```

- [ ] **Step 5: テストが通ることを確認する**

Run: `uv run pytest tests/test_cache.py -v`
Expected: PASS(11 passed)

Run: `uv run pytest`
Expected: 全テスト PASS(45)

Run: `make check`
Expected: エラーなし

- [ ] **Step 6: コミット**

```bash
git add src/yak/cache.py tests/test_cli.py tests/test_cache.py
git commit -m "feat: cache mode classification results"
```

---

### Task 3: CLI と対話モードのモード解決 + README

**Files:**
- Modify: `src/yak/interactive.py`(mode/classifier ベースに変更)
- Modify: `src/yak/main.py`(--translator、envvar、classifier 生成、ディスパッチ)
- Modify: `tests/test_interactive.py`(新シグネチャ追随 + 新テスト)
- Modify: `tests/test_cli.py`(fixture 更新 + 新テスト)
- Modify: `README.md`

**Interfaces:**
- Consumes: `CachingBackend.classify`(Task 2)、`FakeClassifier`(Task 2)、
  `DEFAULT_MODEL` / `DEFAULT_CLASSIFIER_MODEL`(Task 1)
- Produces: `yak.interactive.Mode = Literal["dictionary", "translation", "auto"]`
- Produces: `InteractiveSession(backend, *, mode: Mode, classifier: ModeClassifier | None, from_lang, to_lang)`
  (`dictionary: bool` パラメータは廃止)
- Produces: `yak.main.create_classifier(model: str, *, read_cache: bool = True) -> CachingBackend`

- [ ] **Step 1: 失敗するテストを書く(interactive)**

`tests/test_interactive.py` を修正する。

import を更新:

```python
from tests.test_cli import FakeBackend, FakeClassifier
from yak.interactive import InteractiveSession, Mode, run_interactive
from yak.backends.base import ModeClassifier
```

`_session` ヘルパーを置き換え:

```python
def _session(
    backend: FakeBackend,
    mode: Mode = "translation",
    classifier: ModeClassifier | None = None,
) -> InteractiveSession:
    return InteractiveSession(
        backend,  # type: ignore[arg-type]
        mode=mode,
        classifier=classifier,
        from_lang=None,
        to_lang=None,
    )
```

既存テストの呼び出しを追随させる:
- `_session(backend, dictionary=True)` → `_session(backend, mode="dictionary")`
  (`test_dictionary_mode_line`)
- `test_dictionary_mode_with_translate_only_backend_raises` と
  `test_run_interactive_prints_yak_error_and_continues` 内の
  `InteractiveSession(..., dictionary=True, ...)` →
  `InteractiveSession(..., mode="dictionary", classifier=None, ...)`

末尾に新テストを追記:

```python
def test_auto_mode_classifies_each_line() -> None:
    backend = FakeBackend()
    classifier = FakeClassifier(is_dictionary_entry=True)
    session = _session(backend, mode="auto", classifier=classifier)
    output = session.handle_line("cat")
    assert "意味:" in output
    classifier.decision = False
    assert session.handle_line("hello world") == "こんにちは"
    assert classifier.classify_calls == ["cat", "hello world"]


def test_auto_mode_does_not_classify_bang_lines() -> None:
    backend = FakeBackend()
    classifier = FakeClassifier()
    session = _session(backend, mode="auto", classifier=classifier)
    session.handle_line("!Use polite form.")
    session.handle_line("!")
    assert classifier.classify_calls == []
```

- [ ] **Step 2: 失敗するテストを書く(CLI)**

`tests/test_cli.py` を修正する。

`fake_backend` フィクスチャを置き換え(classifier は「見出し語でない」判定を返す):

```python
@pytest.fixture
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> FakeBackend:
    backend = FakeBackend()
    monkeypatch.setattr("yak.main.create_backend", lambda model, **kwargs: backend)
    monkeypatch.setattr(
        "yak.main.create_classifier",
        lambda model, **kwargs: FakeClassifier(is_dictionary_entry=False),
    )
    return backend
```

`_capture_create_backend` ヘルパーにも classifier のパッチを追加:

```python
def _capture_create_backend(
    monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any]
) -> FakeBackend:
    backend = FakeBackend()

    def fake_create(model: str, *, read_cache: bool = True) -> FakeBackend:
        captured["read_cache"] = read_cache
        return backend

    monkeypatch.setattr("yak.main.create_backend", fake_create)
    monkeypatch.setattr(
        "yak.main.create_classifier",
        lambda model, **kwargs: FakeClassifier(is_dictionary_entry=False),
    )
    return backend
```

末尾に新テストを追記:

```python
def _patch_factories(
    monkeypatch: pytest.MonkeyPatch,
    backend: FakeBackend,
    classifier: FakeClassifier,
) -> None:
    monkeypatch.setattr("yak.main.create_backend", lambda model, **kwargs: backend)
    monkeypatch.setattr(
        "yak.main.create_classifier", lambda model, **kwargs: classifier
    )


def test_auto_mode_dictionary_for_headword(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = FakeBackend()
    classifier = FakeClassifier(is_dictionary_entry=True)
    _patch_factories(monkeypatch, backend, classifier)
    result = CliRunner().invoke(main, ["cat"])
    assert result.exit_code == 0
    assert "意味:" in result.output
    assert classifier.classify_calls == ["cat"]
    assert backend.lookup_calls[0]["text"] == "cat"


def test_auto_mode_translation_for_sentence(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = FakeBackend()
    classifier = FakeClassifier(is_dictionary_entry=False)
    _patch_factories(monkeypatch, backend, classifier)
    result = CliRunner().invoke(main, ["hello world"])
    assert result.exit_code == 0
    assert result.output == "こんにちは\n"
    assert classifier.classify_calls == ["hello world"]


def test_dictionary_flag_skips_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = FakeBackend()
    classifier = FakeClassifier()
    _patch_factories(monkeypatch, backend, classifier)
    result = CliRunner().invoke(main, ["-d", "cat"])
    assert result.exit_code == 0
    assert classifier.classify_calls == []
    assert backend.lookup_calls[0]["text"] == "cat"


def test_translator_flag_skips_classifier(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = FakeBackend()
    classifier = FakeClassifier(is_dictionary_entry=True)
    _patch_factories(monkeypatch, backend, classifier)
    result = CliRunner().invoke(main, ["--translator", "cat"])
    assert result.exit_code == 0
    assert result.output == "こんにちは\n"
    assert classifier.classify_calls == []


def test_dictionary_and_translator_conflict(fake_backend: FakeBackend) -> None:
    result = CliRunner().invoke(main, ["-d", "--translator", "cat"])
    assert result.exit_code == 1
    assert "cannot use --dictionary and --translator together" in result.stderr


def test_model_resolution_option_beats_envvar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_create(model: str, **kwargs: Any) -> FakeBackend:
        captured["model"] = model
        return FakeBackend()

    monkeypatch.setattr("yak.main.create_backend", fake_create)
    monkeypatch.setattr(
        "yak.main.create_classifier", lambda model, **kwargs: FakeClassifier()
    )
    CliRunner().invoke(
        main, ["--translator", "hello"], env={"YAK_MODEL": "env-model"}
    )
    assert captured["model"] == "env-model"
    CliRunner().invoke(
        main,
        ["--translator", "-m", "cli-model", "hello"],
        env={"YAK_MODEL": "env-model"},
    )
    assert captured["model"] == "cli-model"


def test_classifier_model_envvar(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    def fake_classifier_factory(model: str, **kwargs: Any) -> FakeClassifier:
        captured["model"] = model
        return FakeClassifier()

    monkeypatch.setattr(
        "yak.main.create_backend", lambda model, **kwargs: FakeBackend()
    )
    monkeypatch.setattr("yak.main.create_classifier", fake_classifier_factory)
    CliRunner().invoke(main, ["hello"], env={"YAK_CLASSIFIER_MODEL": "nano-x"})
    assert captured["model"] == "nano-x"
```

- [ ] **Step 3: テストが失敗することを確認する**

Run: `uv run pytest tests/test_interactive.py tests/test_cli.py -v`
Expected: FAIL(`TypeError: InteractiveSession.__init__() got an unexpected
keyword argument 'mode'`、`no such option: --translator` など)

- [ ] **Step 4: interactive.py を実装する**

`src/yak/interactive.py` を以下の内容に更新する(全文):

```python
import sys
from collections.abc import Callable
from typing import Literal

from yak.backends.base import DictionaryProvider, ModeClassifier, Translator
from yak.errors import YakError
from yak.render import render_dictionary

Mode = Literal["dictionary", "translation", "auto"]


class InteractiveSession:
    """対話モードの 1 セッション。`!` prefix でシステムプロンプトを追記できる。"""

    def __init__(
        self,
        backend: Translator | DictionaryProvider,
        *,
        mode: Mode,
        classifier: ModeClassifier | None,
        from_lang: str | None,
        to_lang: str | None,
    ) -> None:
        self._backend = backend
        self._mode = mode
        self._classifier = classifier
        self._from_lang = from_lang
        self._to_lang = to_lang
        self._instructions: list[str] = []

    def handle_line(self, line: str) -> str:
        line = line.strip()
        if line == "!":
            self._instructions.clear()
            return "[system prompt をクリアしました]"
        if line.startswith("!"):
            instruction = line[1:].strip()
            self._instructions.append(instruction)
            return f"[system prompt 追加] {instruction}"
        extra = "\n".join(self._instructions) if self._instructions else None
        if self._use_dictionary(line):
            if not isinstance(self._backend, DictionaryProvider):
                raise YakError("this backend does not support dictionary mode")
            return render_dictionary(
                self._backend.lookup(line, self._from_lang, self._to_lang, extra)
            )
        if not isinstance(self._backend, Translator):
            raise YakError("this backend does not support translation mode")
        return self._backend.translate(
            line, self._from_lang, self._to_lang, extra
        ).translated_text

    def _use_dictionary(self, text: str) -> bool:
        if self._mode == "dictionary":
            return True
        if self._mode == "translation":
            return False
        if self._classifier is None:
            raise YakError("auto mode requires a classifier")
        return self._classifier.classify(text).is_dictionary_entry


def run_interactive(
    session: InteractiveSession, *, input_fn: Callable[[str], str] = input
) -> None:
    while True:
        try:
            line = input_fn("yak> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line.strip():
            continue
        try:
            print(session.handle_line(line))
        except YakError as e:
            print(f"yak: {e}", file=sys.stderr)
```

- [ ] **Step 5: main.py を実装する**

`src/yak/main.py` を以下の内容に更新する(全文):

```python
#!/usr/bin/env python

import os
import sys

import click
from openai import OpenAI

from yak.backends.base import DictionaryProvider
from yak.backends.openai import (
    DEFAULT_CLASSIFIER_MODEL,
    DEFAULT_MODEL,
    OpenAIBackend,
)
from yak.cache import CachingBackend, clear_cache, open_cache
from yak.errors import YakError
from yak.interactive import InteractiveSession, Mode, run_interactive
from yak.render import render_dictionary


def create_backend(model: str, *, read_cache: bool = True) -> CachingBackend:
    api_key = os.environ.get("OPENAI_API_KEY_FOR_YAK")
    if not api_key:
        raise YakError("environment variable OPENAI_API_KEY_FOR_YAK is not set")
    inner = OpenAIBackend(OpenAI(api_key=api_key), model)
    return CachingBackend(
        inner,
        open_cache(),
        namespace=f"openai:{model}",
        read_enabled=read_cache,
    )


def create_classifier(model: str, *, read_cache: bool = True) -> CachingBackend:
    """モード自動判定用バックエンド。テストから独立に差し替えられるよう分離する。"""
    return create_backend(model, read_cache=read_cache)


@click.command()
@click.option("--from", "-f", "from_lang", default=None, help="Source language")
@click.option("--to", "-t", "to_lang", default=None, help="Target language")
@click.option("--dictionary", "-d", is_flag=True, help="Force dictionary mode")
@click.option("--translator", is_flag=True, help="Force translation mode")
@click.option(
    "--model",
    "-m",
    envvar="YAK_MODEL",
    default=DEFAULT_MODEL,
    show_default=True,
    help="OpenAI model",
)
@click.option(
    "--classifier-model",
    envvar="YAK_CLASSIFIER_MODEL",
    default=DEFAULT_CLASSIFIER_MODEL,
    show_default=True,
    help="OpenAI model for mode auto-detection",
)
@click.option(
    "--no-cache", is_flag=True, help="Bypass cache reads (results are still saved)"
)
@click.option(
    "--clear-cache", "clear_cache_flag", is_flag=True, help="Clear the cache and exit"
)
@click.argument("text", required=False)
def main(
    from_lang: str | None,
    to_lang: str | None,
    dictionary: bool,
    translator: bool,
    model: str,
    classifier_model: str,
    no_cache: bool,
    clear_cache_flag: bool,
    text: str | None,
) -> None:
    """Translate TEXT (or stdin) with OpenAI."""
    try:
        if clear_cache_flag:
            count = clear_cache()
            click.echo(f"キャッシュをクリアしました ({count} 件)")
            return
        if dictionary and translator:
            raise YakError("cannot use --dictionary and --translator together")
        mode: Mode = (
            "dictionary" if dictionary else "translation" if translator else "auto"
        )
        if text is None:
            if sys.stdin.isatty():
                backend = create_backend(model, read_cache=not no_cache)
                classifier = (
                    create_classifier(classifier_model, read_cache=not no_cache)
                    if mode == "auto"
                    else None
                )
                run_interactive(
                    InteractiveSession(
                        backend,
                        mode=mode,
                        classifier=classifier,
                        from_lang=from_lang,
                        to_lang=to_lang,
                    )
                )
                return
            text = sys.stdin.read().strip()
        if not text:
            raise YakError("no input text")
        backend = create_backend(model, read_cache=not no_cache)
        if mode == "auto":
            classifier = create_classifier(classifier_model, read_cache=not no_cache)
            use_dictionary = classifier.classify(text).is_dictionary_entry
        else:
            use_dictionary = mode == "dictionary"
        if use_dictionary:
            if not isinstance(backend, DictionaryProvider):
                raise YakError("this backend does not support dictionary mode")
            click.echo(
                render_dictionary(backend.lookup(text, from_lang, to_lang, None))
            )
        else:
            click.echo(
                backend.translate(text, from_lang, to_lang, None).translated_text
            )
    except YakError as e:
        click.echo(f"yak: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: テストが通ることを確認する**

Run: `uv run pytest -v`
Expected: 全テスト PASS(54 = 45 + interactive 2 + CLI 7)

Run: `make check`
Expected: エラーなし

- [ ] **Step 7: README を更新する**

`README.md` のオプション表を以下に置き換え:

```markdown
| オプション | 説明 |
|---|---|
| `--from/-f LANG` | 原文の言語 |
| `--to/-t LANG` | 訳先の言語 |
| `--dictionary/-d` | 辞書モードを強制(意味・発音・例文) |
| `--translator` | 翻訳モードを強制 |
| `--model/-m MODEL` | 翻訳・辞書用モデル(envvar: `YAK_MODEL`、デフォルト: `gpt-5-mini`) |
| `--classifier-model MODEL` | モード自動判定用モデル(envvar: `YAK_CLASSIFIER_MODEL`、デフォルト: `gpt-5-nano`) |
| `--no-cache` | キャッシュを読まずに翻訳(結果は保存される) |
| `--clear-cache` | キャッシュを全削除して終了 |
```

言語未指定の説明の後に追記:

```markdown
モード未指定の場合は入力を軽量モデルで判定し、単語・熟語・慣用句などの
「辞書の見出し語」なら辞書モード、文なら翻訳モードで処理する。
```

- [ ] **Step 8: コミット**

```bash
git add src/yak/interactive.py src/yak/main.py \
        tests/test_interactive.py tests/test_cli.py README.md
git commit -m "feat: auto dictionary mode with --translator override"
```

---

### Task 4: 最終確認

**Files:**
- なし(検証のみ。問題があれば該当タスクの範囲で修正)

- [ ] **Step 1: 全体チェック**

Run: `make test`
Expected: mypy / ruff / pytest すべて成功

- [ ] **Step 2: 実 API での動作確認(手動・任意)**

`OPENAI_API_KEY_FOR_YAK` が設定された環境で:

```bash
uv run yak cat            # 自動で辞書モード(意味/発音/例文)
uv run yak "I like cats"  # 自動で翻訳モード
uv run yak --translator cat   # 強制翻訳(「猫」など)
uv run yak -d --translator cat  # エラー
```

Expected: それぞれ仕様どおり。API キーがない環境ではスキップしてよい。

- [ ] **Step 3: 未コミットの修正がないことを確認**

```bash
git status   # クリーンであることを確認
```
