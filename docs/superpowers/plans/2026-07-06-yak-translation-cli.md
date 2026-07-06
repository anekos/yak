# yak 翻訳 CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** OpenAI API を使った翻訳 CLI(通常モード + 辞書モード + 対話モード)を構築する。

**Architecture:** click 製 CLI が `Translator` / `DictionaryProvider` Protocol にのみ依存し、OpenAI バックエンドが Structured Outputs(Pydantic)で常に同一スキーマの応答を返す。バックエンド生成はファクトリ関数 1 つに集約し、将来の Google 翻訳等の追加に備える。

**Tech Stack:** Python 3.13, uv, click, pydantic, openai SDK, pytest, mypy, ruff

**Spec:** `docs/superpowers/specs/2026-07-06-yak-translation-cli-design.md`

## Global Constraints

- Python `>=3.13`、パッケージ管理は uv(依存追加は `uv add`)
- API キーは環境変数 `OPENAI_API_KEY_FOR_YAK` から取得(`OPENAI_API_KEY` は使わない)
- デフォルトモデルは `gpt-4o-mini`、`--model/-m` で上書き可能
- CLI オプション: `--from/-f`, `--to/-t`, `--dictionary/-d`, `--model/-m`
- 通常モードの標準出力は訳文のみ
- 各タスク完了時に `make check`(mypy + ruff)が通ること
- コミットは pre-commit フック(end-of-file-fixer 等)が走る。フックがファイルを修正して
  コミットが失敗したら、`git add` し直して再コミットする
- 発音・例文は「非日本語側の単語」を使う(原文が日本語なら訳語、そうでなければ原語)

---

### Task 1: 依存追加と Pydantic モデル(JSON スキーマ)

**Files:**
- Modify: `pyproject.toml`(uv add 経由)
- Create: `src/yak/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `yak.models.TranslationResult(detected_source_language: str, translated_text: str)`
- Produces: `yak.models.Pronunciation(katakana: str, ipa: str)`
- Produces: `yak.models.DictionaryResult(meanings: list[str], pronunciation: Pronunciation, examples: list[str])`

- [ ] **Step 1: 依存を追加する**

```bash
uv add openai pydantic
```

Expected: `pyproject.toml` の dependencies に `openai` と `pydantic` が追加される。

- [ ] **Step 2: 失敗するテストを書く**

`tests/test_models.py` を作成:

```python
from yak.models import DictionaryResult, Pronunciation, TranslationResult


def test_translation_result_fields() -> None:
    result = TranslationResult(
        detected_source_language="English",
        translated_text="こんにちは",
    )
    assert result.translated_text == "こんにちは"
    assert result.detected_source_language == "English"


def test_dictionary_result_fields() -> None:
    result = DictionaryResult(
        meanings=["猫", "(俗) ねこ"],
        pronunciation=Pronunciation(katakana="キャット", ipa="/kæt/"),
        examples=["The cat sat on the mat."],
    )
    assert result.meanings[0] == "猫"
    assert result.pronunciation.ipa == "/kæt/"
    assert result.examples == ["The cat sat on the mat."]
```

- [ ] **Step 3: テストが失敗することを確認する**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'yak.models'`)

- [ ] **Step 4: モデルを実装する**

`src/yak/models.py` を作成:

```python
from pydantic import BaseModel


class TranslationResult(BaseModel):
    """通常翻訳の結果。OpenAI Structured Outputs のスキーマとしても使う。"""

    detected_source_language: str
    translated_text: str


class Pronunciation(BaseModel):
    katakana: str
    ipa: str


class DictionaryResult(BaseModel):
    """辞書モードの結果。OpenAI Structured Outputs のスキーマとしても使う。"""

    meanings: list[str]
    pronunciation: Pronunciation
    examples: list[str]
```

- [ ] **Step 5: テストが通ることを確認する**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS(2 passed)

Run: `make check`
Expected: mypy / ruff ともエラーなし

- [ ] **Step 6: コミット**

```bash
git add pyproject.toml uv.lock src/yak/models.py tests/test_models.py
git commit -m "feat: add pydantic models for translation and dictionary results"
```

---

### Task 2: 辞書フォーマットのレンダリング

**Files:**
- Create: `src/yak/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `yak.models.DictionaryResult`, `yak.models.Pronunciation`(Task 1)
- Produces: `yak.render.render_dictionary(result: DictionaryResult) -> str`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_render.py` を作成:

```python
from yak.models import DictionaryResult, Pronunciation
from yak.render import render_dictionary


def test_render_dictionary_full() -> None:
    result = DictionaryResult(
        meanings=["猫", "(俗) ねこ、キャット"],
        pronunciation=Pronunciation(katakana="キャット", ipa="/kæt/"),
        examples=["The cat sat on the mat.", "I have a cat."],
    )
    expected = """\
意味:
1. 猫
2. (俗) ねこ、キャット

発音:
キャット / /kæt/

例文:
- The cat sat on the mat.
- I have a cat."""
    assert render_dictionary(result) == expected


def test_render_dictionary_single_items() -> None:
    result = DictionaryResult(
        meanings=["cat"],
        pronunciation=Pronunciation(katakana="キャット", ipa="/kæt/"),
        examples=["I have a cat."],
    )
    text = render_dictionary(result)
    assert "1. cat" in text
    assert "- I have a cat." in text
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run pytest tests/test_render.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'yak.render'`)

- [ ] **Step 3: 実装する**

`src/yak/render.py` を作成:

```python
from yak.models import DictionaryResult


def render_dictionary(result: DictionaryResult) -> str:
    lines = ["意味:"]
    lines.extend(f"{i}. {meaning}" for i, meaning in enumerate(result.meanings, 1))
    lines.append("")
    lines.append("発音:")
    lines.append(f"{result.pronunciation.katakana} / {result.pronunciation.ipa}")
    lines.append("")
    lines.append("例文:")
    lines.extend(f"- {example}" for example in result.examples)
    return "\n".join(lines)
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `uv run pytest tests/test_render.py -v`
Expected: PASS(2 passed)

Run: `make check`
Expected: エラーなし

- [ ] **Step 5: コミット**

```bash
git add src/yak/render.py tests/test_render.py
git commit -m "feat: add dictionary output rendering"
```

---

### Task 3: エラー型とバックエンド Protocol

**Files:**
- Create: `src/yak/errors.py`
- Create: `src/yak/backends/__init__.py`
- Create: `src/yak/backends/base.py`

**Interfaces:**
- Consumes: `yak.models.TranslationResult`, `yak.models.DictionaryResult`(Task 1)
- Produces: `yak.errors.YakError`(ユーザー向けエラーはすべてこれで表現する)
- Produces: `yak.backends.base.Translator` Protocol —
  `translate(text: str, from_lang: str | None, to_lang: str | None, extra_instruction: str | None) -> TranslationResult`
- Produces: `yak.backends.base.DictionaryProvider` Protocol —
  `lookup(text: str, from_lang: str | None, to_lang: str | None, extra_instruction: str | None) -> DictionaryResult`

Protocol と例外クラスのみで実行時ロジックがないため、このタスクは型チェックを
テストとみなす(ユニットテストは書かない)。

- [ ] **Step 1: エラー型を実装する**

`src/yak/errors.py` を作成:

```python
class YakError(Exception):
    """ユーザーに表示するエラー。CLI はこれを捕捉して stderr + exit 1 にする。"""
```

- [ ] **Step 2: Protocol を実装する**

`src/yak/backends/__init__.py` を空ファイルとして作成。

`src/yak/backends/base.py` を作成:

```python
from typing import Protocol

from yak.models import DictionaryResult, TranslationResult


class Translator(Protocol):
    """翻訳バックエンドの共通インターフェイス。

    Google 翻訳などの非 LLM バックエンドはこれのみ実装する。
    """

    def translate(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> TranslationResult: ...


class DictionaryProvider(Protocol):
    """辞書モードを提供できるバックエンドのインターフェイス。"""

    def lookup(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> DictionaryResult: ...
```

- [ ] **Step 3: 型チェックが通ることを確認する**

Run: `make check`
Expected: mypy / ruff ともエラーなし

Run: `uv run pytest`
Expected: 既存テストがすべて PASS のまま

- [ ] **Step 4: コミット**

```bash
git add src/yak/errors.py src/yak/backends/__init__.py src/yak/backends/base.py
git commit -m "feat: add YakError and backend protocols"
```

---

### Task 4: OpenAI バックエンド

**Files:**
- Create: `src/yak/backends/openai.py`
- Test: `tests/test_openai_backend.py`

**Interfaces:**
- Consumes: `yak.models.*`(Task 1)、`yak.errors.YakError`(Task 3)
- Produces: `yak.backends.openai.DEFAULT_MODEL = "gpt-4o-mini"`
- Produces: `yak.backends.openai.language_instruction(from_lang: str | None, to_lang: str | None) -> str`
- Produces: `yak.backends.openai.OpenAIBackend(client: OpenAI, model: str)` —
  `Translator` と `DictionaryProvider` の両 Protocol を満たす

- [ ] **Step 1: language_instruction の失敗するテストを書く**

`tests/test_openai_backend.py` を作成:

```python
from typing import Any, cast

import pytest
from openai import OpenAI

from yak.backends.openai import OpenAIBackend, language_instruction
from yak.errors import YakError
from yak.models import DictionaryResult, Pronunciation, TranslationResult


def test_language_instruction_both_specified() -> None:
    text = language_instruction("English", "French")
    assert "English" in text
    assert "French" in text


def test_language_instruction_to_only() -> None:
    text = language_instruction(None, "German")
    assert "German" in text
    assert "detect" in text.lower()


def test_language_instruction_from_only() -> None:
    text = language_instruction("French", None)
    assert "French" in text
    assert "Japanese" in text


def test_language_instruction_none() -> None:
    text = language_instruction(None, None)
    assert "Japanese" in text
    assert "English" in text
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run pytest tests/test_openai_backend.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'yak.backends.openai'`)

- [ ] **Step 3: language_instruction を実装する**

`src/yak/backends/openai.py` を作成:

```python
from openai import OpenAI, OpenAIError
from pydantic import BaseModel

from yak.errors import YakError
from yak.models import DictionaryResult, TranslationResult

DEFAULT_MODEL = "gpt-4o-mini"


def language_instruction(from_lang: str | None, to_lang: str | None) -> str:
    """--from/--to の指定状況から言語決定の指示文を組み立てる。

    未指定時は英日ペアとみなし、原文と逆の言語へ翻訳する(spec の言語決定ルール)。
    """
    if from_lang and to_lang:
        return f"Translate the text from {from_lang} to {to_lang}."
    if to_lang:
        return f"Detect the language of the text and translate it to {to_lang}."
    if from_lang:
        return (
            f"The text is in {from_lang}. "
            "If that language is English, translate to Japanese; "
            "if it is Japanese, translate to English; "
            "otherwise translate to Japanese."
        )
    return (
        "Detect the language of the text. "
        "If it is Japanese, translate to English; otherwise translate to Japanese."
    )
```

- [ ] **Step 4: language_instruction のテストが通ることを確認する**

Run: `uv run pytest tests/test_openai_backend.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: OpenAIBackend の失敗するテストを追記する**

`tests/test_openai_backend.py` に追記:

```python
class _FakeMessage:
    def __init__(self, parsed: Any) -> None:
        self.parsed = parsed


class _FakeChoice:
    def __init__(self, parsed: Any) -> None:
        self.message = _FakeMessage(parsed)


class _FakeCompletion:
    def __init__(self, parsed: Any) -> None:
        self.choices = [_FakeChoice(parsed)]


class _FakeClient:
    """OpenAI クライアントの代役。parse() 呼び出しを記録して固定値を返す。"""

    def __init__(self, parsed: Any) -> None:
        self.calls: list[dict[str, Any]] = []
        outer = self

        class _Completions:
            def parse(self, **kwargs: Any) -> _FakeCompletion:
                outer.calls.append(kwargs)
                return _FakeCompletion(parsed)

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


def _backend(parsed: Any) -> tuple[OpenAIBackend, _FakeClient]:
    fake = _FakeClient(parsed)
    return OpenAIBackend(cast(OpenAI, fake), "test-model"), fake


def test_translate_returns_parsed_result() -> None:
    expected = TranslationResult(
        detected_source_language="English", translated_text="こんにちは"
    )
    backend, fake = _backend(expected)
    result = backend.translate("hello", None, None, None)
    assert result == expected
    call = fake.calls[0]
    assert call["model"] == "test-model"
    assert call["response_format"] is TranslationResult
    assert call["messages"][1] == {"role": "user", "content": "hello"}


def test_translate_includes_extra_instruction() -> None:
    expected = TranslationResult(
        detected_source_language="English", translated_text="こんにちは"
    )
    backend, fake = _backend(expected)
    backend.translate("hello", None, None, "Use polite form.")
    system = fake.calls[0]["messages"][0]["content"]
    assert "Use polite form." in system


def test_lookup_returns_parsed_result() -> None:
    expected = DictionaryResult(
        meanings=["猫"],
        pronunciation=Pronunciation(katakana="キャット", ipa="/kæt/"),
        examples=["I have a cat."],
    )
    backend, fake = _backend(expected)
    result = backend.lookup("cat", None, None, None)
    assert result == expected
    assert fake.calls[0]["response_format"] is DictionaryResult


def test_translate_raises_yak_error_on_none_parsed() -> None:
    backend, _ = _backend(None)
    with pytest.raises(YakError):
        backend.translate("hello", None, None, None)
```

- [ ] **Step 6: テストが失敗することを確認する**

Run: `uv run pytest tests/test_openai_backend.py -v`
Expected: FAIL(`ImportError: cannot import name 'OpenAIBackend'`)

- [ ] **Step 7: OpenAIBackend を実装する**

`src/yak/backends/openai.py` に追記:

```python
_TRANSLATE_SYSTEM = (
    "You are a translation engine. {languages} "
    "Preserve the meaning, tone, and register of the original text. "
    "Set detected_source_language to the language of the input text."
)

_DICTIONARY_SYSTEM = (
    "You are a bilingual dictionary. {languages} "
    "The input is a word or short phrase. Respond with: "
    "meanings — the senses of the input translated into the target language, "
    "with register or nuance notes where relevant; "
    "pronunciation — katakana reading and IPA; "
    "examples — a few example sentences. "
    "For pronunciation and examples, use the non-Japanese side of the pair: "
    "if the input is Japanese, use the translated word; "
    "otherwise use the input word itself."
)


class OpenAIBackend:
    """Translator / DictionaryProvider の OpenAI 実装。"""

    def __init__(self, client: OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    def translate(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> TranslationResult:
        system = _TRANSLATE_SYSTEM.format(
            languages=language_instruction(from_lang, to_lang)
        )
        return self._parse(system, text, extra_instruction, TranslationResult)

    def lookup(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> DictionaryResult:
        system = _DICTIONARY_SYSTEM.format(
            languages=language_instruction(from_lang, to_lang)
        )
        return self._parse(system, text, extra_instruction, DictionaryResult)

    def _parse[T: BaseModel](
        self,
        system: str,
        text: str,
        extra_instruction: str | None,
        response_format: type[T],
    ) -> T:
        if extra_instruction:
            system = f"{system}\n\nAdditional instructions:\n{extra_instruction}"
        try:
            completion = self._client.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                response_format=response_format,
            )
        except OpenAIError as e:
            raise YakError(f"OpenAI API error: {e}") from e
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise YakError("OpenAI returned an empty response")
        return parsed
```

- [ ] **Step 8: テストが通ることを確認する**

Run: `uv run pytest tests/test_openai_backend.py -v`
Expected: PASS(8 passed)

Run: `make check`
Expected: エラーなし

- [ ] **Step 9: コミット**

```bash
git add src/yak/backends/openai.py tests/test_openai_backend.py
git commit -m "feat: add OpenAI backend with structured outputs"
```

---

### Task 5: CLI(通常モード・辞書モード・stdin パイプ)

**Files:**
- Modify: `src/yak/main.py`(Hello World を置き換える)
- Create: `tests/__init__.py`(空ファイル。テスト間 import(Task 6)と mypy のため)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `OpenAIBackend`, `DEFAULT_MODEL`(Task 4)、`render_dictionary`(Task 2)、
  `YakError`(Task 3)
- Produces: `yak.main.create_backend(model: str) -> OpenAIBackend`
  (環境変数 `OPENAI_API_KEY_FOR_YAK` を読む唯一の場所。将来のバックエンド追加もここを拡張する)
- Produces: `yak.main.main` — click コマンド(エントリポイント `yak` は既存の
  `pyproject.toml` の `yak = "yak.main:main"` をそのまま使う)

対話モード(stdin が端末のケース)は Task 6 で実装する。このタスクの時点では、
TEXT なし & stdin が端末なら「no input text」エラーにしておく。

- [ ] **Step 1: 失敗するテストを書く**

`tests/__init__.py` を空ファイルとして作成する(pytest がプロジェクトルートを
sys.path に入れるようにするため。Task 6 で `tests.test_cli` を import する)。

`tests/test_cli.py` を作成:

```python
from typing import Any

import pytest
from click.testing import CliRunner

from yak.main import main
from yak.models import DictionaryResult, Pronunciation, TranslationResult


class FakeBackend:
    def __init__(self) -> None:
        self.translate_calls: list[dict[str, Any]] = []
        self.lookup_calls: list[dict[str, Any]] = []

    def translate(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> TranslationResult:
        self.translate_calls.append(
            {"text": text, "from": from_lang, "to": to_lang}
        )
        return TranslationResult(
            detected_source_language="English", translated_text="こんにちは"
        )

    def lookup(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> DictionaryResult:
        self.lookup_calls.append({"text": text, "from": from_lang, "to": to_lang})
        return DictionaryResult(
            meanings=["猫"],
            pronunciation=Pronunciation(katakana="キャット", ipa="/kæt/"),
            examples=["I have a cat."],
        )


@pytest.fixture
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> FakeBackend:
    backend = FakeBackend()
    monkeypatch.setattr("yak.main.create_backend", lambda model: backend)
    return backend


def test_translate_text_argument(fake_backend: FakeBackend) -> None:
    result = CliRunner().invoke(main, ["hello"])
    assert result.exit_code == 0
    assert result.output == "こんにちは\n"
    assert fake_backend.translate_calls[0]["text"] == "hello"


def test_translate_passes_languages(fake_backend: FakeBackend) -> None:
    result = CliRunner().invoke(main, ["-f", "English", "-t", "French", "hello"])
    assert result.exit_code == 0
    call = fake_backend.translate_calls[0]
    assert call["from"] == "English"
    assert call["to"] == "French"


def test_dictionary_mode(fake_backend: FakeBackend) -> None:
    result = CliRunner().invoke(main, ["-d", "cat"])
    assert result.exit_code == 0
    assert "意味:" in result.output
    assert "1. 猫" in result.output
    assert "キャット / /kæt/" in result.output
    assert fake_backend.lookup_calls[0]["text"] == "cat"


def test_reads_stdin_when_no_argument(fake_backend: FakeBackend) -> None:
    result = CliRunner().invoke(main, [], input="hello from pipe\n")
    assert result.exit_code == 0
    assert fake_backend.translate_calls[0]["text"] == "hello from pipe"


def test_empty_input_is_error(fake_backend: FakeBackend) -> None:
    result = CliRunner().invoke(main, [], input="")
    assert result.exit_code == 1
    assert "no input text" in result.stderr


def test_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY_FOR_YAK", raising=False)
    result = CliRunner().invoke(main, ["hello"])
    assert result.exit_code == 1
    assert "OPENAI_API_KEY_FOR_YAK" in result.stderr
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL(`ImportError: cannot import name 'create_backend'` 等)

- [ ] **Step 3: CLI を実装する**

`src/yak/main.py` を全面的に書き換える:

```python
#!/usr/bin/env python

import os
import sys

import click
from openai import OpenAI

from yak.backends.openai import DEFAULT_MODEL, OpenAIBackend
from yak.errors import YakError
from yak.render import render_dictionary


def create_backend(model: str) -> OpenAIBackend:
    api_key = os.environ.get("OPENAI_API_KEY_FOR_YAK")
    if not api_key:
        raise YakError("environment variable OPENAI_API_KEY_FOR_YAK is not set")
    return OpenAIBackend(OpenAI(api_key=api_key), model)


@click.command()
@click.option("--from", "-f", "from_lang", default=None, help="Source language")
@click.option("--to", "-t", "to_lang", default=None, help="Target language")
@click.option("--dictionary", "-d", is_flag=True, help="Dictionary mode")
@click.option("--model", "-m", default=DEFAULT_MODEL, show_default=True)
@click.argument("text", required=False)
def main(
    from_lang: str | None,
    to_lang: str | None,
    dictionary: bool,
    model: str,
    text: str | None,
) -> None:
    """Translate TEXT (or stdin) with OpenAI."""
    try:
        if text is None:
            if sys.stdin.isatty():
                raise YakError("no input text")  # Task 6 で対話モードに置き換える
            text = sys.stdin.read().strip()
        if not text:
            raise YakError("no input text")
        backend = create_backend(model)
        if dictionary:
            click.echo(render_dictionary(backend.lookup(text, from_lang, to_lang, None)))
        else:
            click.echo(backend.translate(text, from_lang, to_lang, None).translated_text)
    except YakError as e:
        click.echo(f"yak: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: テストが通ることを確認する**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS(6 passed)

Run: `make check`
Expected: エラーなし

- [ ] **Step 5: コミット**

```bash
git add src/yak/main.py tests/__init__.py tests/test_cli.py
git commit -m "feat: add CLI with normal and dictionary modes"
```

---

### Task 6: 対話モードと README

**Files:**
- Create: `src/yak/interactive.py`
- Modify: `src/yak/main.py`(端末時に対話モードへ分岐)
- Modify: `README.md`
- Test: `tests/test_interactive.py`

**Interfaces:**
- Consumes: `Translator`/`DictionaryProvider` を満たすバックエンド(Task 3/4)、
  `render_dictionary`(Task 2)、`YakError`(Task 3)
- Produces: `yak.interactive.InteractiveSession(backend: OpenAIBackend, *, dictionary: bool, from_lang: str | None, to_lang: str | None)` —
  `handle_line(line: str) -> str`
- Produces: `yak.interactive.run_interactive(session: InteractiveSession) -> None`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_interactive.py` を作成(FakeBackend は tests/test_cli.py のものを import):

```python
from tests.test_cli import FakeBackend
from yak.interactive import InteractiveSession


def _session(backend: FakeBackend, dictionary: bool = False) -> InteractiveSession:
    return InteractiveSession(
        backend,  # type: ignore[arg-type]
        dictionary=dictionary,
        from_lang=None,
        to_lang=None,
    )


def test_translates_plain_line() -> None:
    backend = FakeBackend()
    session = _session(backend)
    assert session.handle_line("hello") == "こんにちは"
    assert backend.translate_calls[0]["text"] == "hello"


def test_dictionary_mode_line() -> None:
    backend = FakeBackend()
    session = _session(backend, dictionary=True)
    output = session.handle_line("cat")
    assert "意味:" in output
    assert backend.lookup_calls[0]["text"] == "cat"


def test_bang_appends_system_prompt_with_feedback() -> None:
    backend = FakeBackend()
    session = _session(backend)
    feedback = session.handle_line("!Use polite form.")
    assert "[system prompt 追加]" in feedback
    assert "Use polite form." in feedback
    session.handle_line("hello")
    assert backend.translate_calls[0]["extra"] == "Use polite form."


def test_bang_accumulates_instructions() -> None:
    backend = FakeBackend()
    session = _session(backend)
    session.handle_line("!First.")
    session.handle_line("!Second.")
    session.handle_line("hello")
    assert backend.translate_calls[0]["extra"] == "First.\nSecond."


def test_bang_alone_clears_with_feedback() -> None:
    backend = FakeBackend()
    session = _session(backend)
    session.handle_line("!First.")
    feedback = session.handle_line("!")
    assert "クリア" in feedback
    session.handle_line("hello")
    assert backend.translate_calls[0]["extra"] is None
```

`tests/test_cli.py` の `FakeBackend` に `extra` の記録を追加する
(translate_calls / lookup_calls の dict に `"extra": extra_instruction` を追加):

```python
        self.translate_calls.append(
            {"text": text, "from": from_lang, "to": to_lang, "extra": extra_instruction}
        )
```

```python
        self.lookup_calls.append(
            {"text": text, "from": from_lang, "to": to_lang, "extra": extra_instruction}
        )
```

- [ ] **Step 2: テストが失敗することを確認する**

Run: `uv run pytest tests/test_interactive.py -v`
Expected: FAIL(`ModuleNotFoundError: No module named 'yak.interactive'`)

- [ ] **Step 3: 対話モードを実装する**

`src/yak/interactive.py` を作成:

```python
import sys

from yak.backends.base import DictionaryProvider, Translator
from yak.errors import YakError
from yak.render import render_dictionary


class InteractiveSession:
    """対話モードの 1 セッション。`!` prefix でシステムプロンプトを追記できる。"""

    def __init__(
        self,
        backend: Translator | DictionaryProvider,
        *,
        dictionary: bool,
        from_lang: str | None,
        to_lang: str | None,
    ) -> None:
        self._backend = backend
        self._dictionary = dictionary
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
        if self._dictionary:
            assert isinstance(self._backend, DictionaryProvider)
            return render_dictionary(
                self._backend.lookup(line, self._from_lang, self._to_lang, extra)
            )
        assert isinstance(self._backend, Translator)
        return self._backend.translate(
            line, self._from_lang, self._to_lang, extra
        ).translated_text


def run_interactive(session: InteractiveSession) -> None:
    while True:
        try:
            line = input("yak> ")
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

注意: `Protocol` に対する `isinstance` チェックには `@runtime_checkable` が必要。
`src/yak/backends/base.py` を以下の内容に更新する(デコレータと import の追加のみ):

```python
from typing import Protocol, runtime_checkable

from yak.models import DictionaryResult, TranslationResult


@runtime_checkable
class Translator(Protocol):
    """翻訳バックエンドの共通インターフェイス。

    Google 翻訳などの非 LLM バックエンドはこれのみ実装する。
    """

    def translate(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> TranslationResult: ...


@runtime_checkable
class DictionaryProvider(Protocol):
    """辞書モードを提供できるバックエンドのインターフェイス。"""

    def lookup(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> DictionaryResult: ...
```

- [ ] **Step 4: main.py を対話モードに接続する**

`src/yak/main.py` の `raise YakError("no input text")  # Task 6 で...` の分岐を置き換える:

```python
        if text is None:
            if sys.stdin.isatty():
                backend = create_backend(model)
                run_interactive(
                    InteractiveSession(
                        backend,
                        dictionary=dictionary,
                        from_lang=from_lang,
                        to_lang=to_lang,
                    )
                )
                return
            text = sys.stdin.read().strip()
```

import も追加する:

```python
from yak.interactive import InteractiveSession, run_interactive
```

- [ ] **Step 5: テストが通ることを確認する**

Run: `uv run pytest -v`
Expected: 全テスト PASS(対話モード 5 + 既存すべて)

Run: `make check`
Expected: エラーなし

- [ ] **Step 6: README を書く**

`README.md` を以下の内容に書き換える:

````markdown
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
````

- [ ] **Step 7: コミット**

```bash
git add src/yak/interactive.py src/yak/main.py src/yak/backends/base.py \
        tests/test_interactive.py tests/test_cli.py README.md
git commit -m "feat: add interactive mode with session system prompts"
```

---

### Task 7: 最終確認

**Files:**
- なし(検証のみ。問題があれば該当タスクの範囲で修正)

- [ ] **Step 1: 全体チェック**

Run: `make test`
Expected: mypy / ruff / pytest すべて成功

- [ ] **Step 2: 実 API での動作確認(手動・任意)**

`OPENAI_API_KEY_FOR_YAK` が設定された環境で:

```bash
uv run yak hello                  # 日本語訳が出る
uv run yak -d cat                 # 辞書フォーマットが出る
echo "猫が好き" | uv run yak       # 英語訳が出る
```

Expected: それぞれ仕様どおりの出力。API キーがない環境ではスキップしてよい。

- [ ] **Step 3: 未コミットの修正があればコミット**

```bash
git status   # クリーンであることを確認
```
