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
