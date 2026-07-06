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
