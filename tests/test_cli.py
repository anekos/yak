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
        self.translate_calls.append({"text": text, "from": from_lang, "to": to_lang})
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
