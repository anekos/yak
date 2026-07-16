from collections.abc import Callable

import pytest

from tests.test_cli import FakeBackend, FakeClassifier
from yak.backends.base import ModeClassifier
from yak.errors import YakError
from yak.interactive import InteractiveSession, Mode, run_interactive
from yak.models import AnswerResult, DictionaryResult, Pronunciation, TranslationResult


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


class TranslateOnlyBackend:
    """`lookup` を持たない、翻訳専用のバックエンド。"""

    def translate(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> TranslationResult:
        return TranslationResult(
            detected_source_language="English", translated_text="こんにちは"
        )


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


def test_translates_plain_line() -> None:
    backend = FakeBackend()
    session = _session(backend)
    assert session.handle_line("hello") == "こんにちは"
    assert backend.translate_calls[0]["text"] == "hello"


def test_dictionary_mode_line() -> None:
    backend = FakeBackend()
    session = _session(backend, mode="dictionary")
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


def test_question_mark_asks_question() -> None:
    backend = FakeBackend()
    session = _session(backend)
    assert session.handle_line("? What does this mean?") == "回答です。"
    assert backend.ask_calls[0]["question"] == "What does this mean?"
    assert backend.ask_calls[0]["context"] is None


def test_question_includes_session_context() -> None:
    backend = FakeBackend()
    session = _session(backend)
    session.handle_line("hello")
    session.handle_line("? なぜこの訳になるの?")
    context = backend.ask_calls[0]["context"]
    assert context is not None
    assert "hello" in context
    assert "こんにちは" in context


def test_question_exchange_is_added_to_context() -> None:
    backend = FakeBackend()
    session = _session(backend)
    session.handle_line("? first question")
    session.handle_line("? second question")
    context = backend.ask_calls[1]["context"]
    assert context is not None
    assert "first question" in context
    assert "回答です。" in context


def test_question_context_is_capped() -> None:
    backend = FakeBackend()
    session = _session(backend)
    for i in range(25):
        session.handle_line(f"line {i}")
    session.handle_line("? question")
    context = backend.ask_calls[0]["context"]
    assert context is not None
    assert "line 4" not in context
    assert "line 5" in context
    assert "line 24" in context


def test_question_uses_extra_instructions() -> None:
    backend = FakeBackend()
    session = _session(backend)
    session.handle_line("!Use polite form.")
    session.handle_line("? question")
    assert backend.ask_calls[0]["extra"] == "Use polite form."


def test_question_mark_alone_raises() -> None:
    session = _session(FakeBackend())
    with pytest.raises(YakError):
        session.handle_line("?")


def test_question_with_translate_only_backend_raises() -> None:
    session = InteractiveSession(
        TranslateOnlyBackend(),  # type: ignore[arg-type]
        mode="translation",
        classifier=None,
        from_lang=None,
        to_lang=None,
    )
    with pytest.raises(YakError, match="question mode"):
        session.handle_line("? question")


def test_auto_mode_does_not_classify_question_lines() -> None:
    backend = FakeBackend()
    classifier = FakeClassifier()
    session = _session(backend, mode="auto", classifier=classifier)
    session.handle_line("? question")
    assert classifier.classify_calls == []


def test_oneline_question_joins_lines() -> None:
    class MultilineAnswerBackend:
        def ask(
            self,
            question: str,
            context: str | None,
            extra_instruction: str | None,
        ) -> AnswerResult:
            return AnswerResult(answer="一行目。\n\n二行目。")

    session = InteractiveSession(
        MultilineAnswerBackend(),  # type: ignore[arg-type]
        mode="translation",
        classifier=None,
        from_lang=None,
        to_lang=None,
        oneline=True,
    )
    assert session.handle_line("? question") == "一行目。 二行目。"


def test_dictionary_mode_with_translate_only_backend_raises() -> None:
    backend = TranslateOnlyBackend()
    session = InteractiveSession(
        backend,  # type: ignore[arg-type]
        mode="dictionary",
        classifier=None,
        from_lang=None,
        to_lang=None,
    )
    with pytest.raises(YakError):
        session.handle_line("word")


def _input_fn_from(*lines: str) -> Callable[[str], str]:
    iterator = iter(lines)

    def _input(prompt: str) -> str:
        try:
            return next(iterator)
        except StopIteration:
            raise EOFError() from None

    return _input


def test_run_interactive_returns_on_eof() -> None:
    session = _session(FakeBackend())

    def input_fn(prompt: str) -> str:
        raise EOFError()

    run_interactive(session, input_fn=input_fn)


def test_run_interactive_returns_on_keyboard_interrupt() -> None:
    session = _session(FakeBackend())

    def input_fn(prompt: str) -> str:
        raise KeyboardInterrupt()

    run_interactive(session, input_fn=input_fn)


def test_run_interactive_prints_yak_error_and_continues(
    capsys: pytest.CaptureFixture[str],
) -> None:
    session = InteractiveSession(
        TranslateOnlyBackend(),  # type: ignore[arg-type]
        mode="dictionary",
        classifier=None,
        from_lang=None,
        to_lang=None,
    )
    run_interactive(session, input_fn=_input_fn_from("word", "another"))
    captured = capsys.readouterr()
    assert captured.err.count("yak:") == 2


def test_run_interactive_skips_empty_lines() -> None:
    backend = FakeBackend()
    session = _session(backend)
    run_interactive(session, input_fn=_input_fn_from("   ", "", "hello"))
    assert backend.translate_calls[0]["text"] == "hello"


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
