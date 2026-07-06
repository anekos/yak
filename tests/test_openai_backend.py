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
