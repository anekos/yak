from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from yak.cache import open_cache
from yak.main import main
from yak.models import (
    AnswerResult,
    DictionaryResult,
    ModeDecision,
    Pronunciation,
    TranslationResult,
)


class FakeBackend:
    def __init__(self) -> None:
        self.translate_calls: list[dict[str, Any]] = []
        self.lookup_calls: list[dict[str, Any]] = []
        self.ask_calls: list[dict[str, Any]] = []

    def translate(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> TranslationResult:
        self.translate_calls.append(
            {"text": text, "from": from_lang, "to": to_lang, "extra": extra_instruction}
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
        self.lookup_calls.append(
            {"text": text, "from": from_lang, "to": to_lang, "extra": extra_instruction}
        )
        return DictionaryResult(
            meanings=["猫"],
            pronunciation=Pronunciation(katakana="キャット", ipa="/kæt/"),
            examples=["I have a cat."],
        )

    def ask(
        self,
        question: str,
        context: str | None,
        extra_instruction: str | None,
    ) -> AnswerResult:
        self.ask_calls.append(
            {"question": question, "context": context, "extra": extra_instruction}
        )
        return AnswerResult(answer="回答です。")


class FakeClassifier:
    def __init__(self, is_dictionary_entry: bool = False) -> None:
        self.decision = is_dictionary_entry
        self.classify_calls: list[str] = []

    def classify(self, text: str) -> ModeDecision:
        self.classify_calls.append(text)
        return ModeDecision(is_dictionary_entry=self.decision)


@pytest.fixture
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> FakeBackend:
    backend = FakeBackend()
    monkeypatch.setattr("yak.main.create_backend", lambda model, **kwargs: backend)
    monkeypatch.setattr(
        "yak.main.create_classifier",
        lambda model, **kwargs: FakeClassifier(is_dictionary_entry=False),
    )
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


def _capture_create_backend(
    monkeypatch: pytest.MonkeyPatch, captured: dict[str, Any]
) -> FakeBackend:
    backend = FakeBackend()

    def fake_create(model: str, **kwargs: Any) -> FakeBackend:
        captured.update(kwargs)
        return backend

    monkeypatch.setattr("yak.main.create_backend", fake_create)
    monkeypatch.setattr(
        "yak.main.create_classifier",
        lambda model, **kwargs: FakeClassifier(is_dictionary_entry=False),
    )
    return backend


def test_no_cache_disables_cache_read(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _capture_create_backend(monkeypatch, captured)
    result = CliRunner().invoke(main, ["--no-cache", "hello"])
    assert result.exit_code == 0
    assert captured["read_cache"] is False


def test_cache_read_enabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _capture_create_backend(monkeypatch, captured)
    result = CliRunner().invoke(main, ["hello"])
    assert result.exit_code == 0
    assert captured["read_cache"] is True


def test_clear_cache_clears_and_exits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY_FOR_YAK", raising=False)
    monkeypatch.setattr("yak.cache.cache_directory", lambda: tmp_path / "cache")
    with open_cache() as cache:
        cache["a"] = 1
        cache["b"] = 2
    result = CliRunner().invoke(main, ["--clear-cache"])
    assert result.exit_code == 0
    assert "キャッシュをクリアしました (2 件)" in result.output


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
    CliRunner().invoke(main, ["--translator", "hello"], env={"YAK_MODEL": "env-model"})
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


def test_reasoning_effort_defaults_to_minimal(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _capture_create_backend(monkeypatch, captured)
    result = CliRunner().invoke(main, ["--translator", "hello"])
    assert result.exit_code == 0
    assert captured["reasoning_effort"] == "minimal"


def test_reasoning_effort_option_beats_envvar(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    _capture_create_backend(monkeypatch, captured)
    CliRunner().invoke(
        main, ["--translator", "hello"], env={"YAK_REASONING_EFFORT": "low"}
    )
    assert captured["reasoning_effort"] == "low"
    CliRunner().invoke(
        main,
        ["--translator", "-r", "high", "hello"],
        env={"YAK_REASONING_EFFORT": "low"},
    )
    assert captured["reasoning_effort"] == "high"


def test_reasoning_effort_rejects_unknown_value(fake_backend: FakeBackend) -> None:
    result = CliRunner().invoke(main, ["-r", "turbo", "hello"])
    assert result.exit_code != 0


def test_reasoning_effort_applies_to_classifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_classifier_factory(model: str, **kwargs: Any) -> FakeClassifier:
        captured.update(kwargs)
        return FakeClassifier()

    monkeypatch.setattr(
        "yak.main.create_backend", lambda model, **kwargs: FakeBackend()
    )
    monkeypatch.setattr("yak.main.create_classifier", fake_classifier_factory)
    CliRunner().invoke(main, ["-r", "low", "hello"])
    assert captured["reasoning_effort"] == "low"


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
