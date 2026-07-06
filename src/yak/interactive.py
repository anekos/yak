import sys
from collections.abc import Callable

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
