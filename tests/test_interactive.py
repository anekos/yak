from collections.abc import Callable

import pytest

from tests.test_cli import FakeBackend
from yak.errors import YakError
from yak.interactive import InteractiveSession, run_interactive
from yak.models import TranslationResult


def _session(backend: FakeBackend, dictionary: bool = False) -> InteractiveSession:
    return InteractiveSession(
        backend,  # type: ignore[arg-type]
        dictionary=dictionary,
        from_lang=None,
        to_lang=None,
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


def test_dictionary_mode_with_translate_only_backend_raises() -> None:
    backend = TranslateOnlyBackend()
    session = InteractiveSession(
        backend,  # type: ignore[arg-type]
        dictionary=True,
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
    backend = FakeBackend()
    session = InteractiveSession(
        TranslateOnlyBackend(),  # type: ignore[arg-type]
        dictionary=True,
        from_lang=None,
        to_lang=None,
    )
    run_interactive(session, input_fn=_input_fn_from("word", "another"))
    captured = capsys.readouterr()
    assert captured.err.count("yak:") == 2
    assert backend.lookup_calls == []


def test_run_interactive_skips_empty_lines() -> None:
    backend = FakeBackend()
    session = _session(backend)
    run_interactive(session, input_fn=_input_fn_from("   ", "", "hello"))
    assert backend.translate_calls[0]["text"] == "hello"
