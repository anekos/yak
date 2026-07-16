import sys
from collections.abc import Callable
from typing import Literal

from yak.backends.base import (
    DictionaryProvider,
    ModeClassifier,
    QuestionAnswerer,
    Translator,
)
from yak.errors import YakError
from yak.render import oneline_text, render_dictionary

Mode = Literal["dictionary", "translation", "auto"]

# 質問モードに渡すセッション文脈の上限(プロンプトの肥大化を防ぐ)。
MAX_CONTEXT_ENTRIES = 20


class InteractiveSession:
    """対話モードの 1 セッション。

    `!` prefix でシステムプロンプトを追記、`?` prefix でセッションの文脈を
    踏まえた質問ができる。
    """

    def __init__(
        self,
        backend: Translator | DictionaryProvider,
        *,
        mode: Mode,
        classifier: ModeClassifier | None,
        from_lang: str | None,
        to_lang: str | None,
        oneline: bool = False,
    ) -> None:
        self._backend = backend
        self._mode = mode
        self._classifier = classifier
        self._from_lang = from_lang
        self._to_lang = to_lang
        self._oneline = oneline
        self._instructions: list[str] = []
        self._context: list[tuple[str, str]] = []

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
        if line.startswith("?"):
            return self._answer(line[1:].strip(), extra)
        if self._use_dictionary(line):
            if not isinstance(self._backend, DictionaryProvider):
                raise YakError("this backend does not support dictionary mode")
            rendered = render_dictionary(
                self._backend.lookup(line, self._from_lang, self._to_lang, extra),
                oneline=self._oneline,
            )
            self._remember(line, rendered)
            return rendered
        if not isinstance(self._backend, Translator):
            raise YakError("this backend does not support translation mode")
        translated = self._backend.translate(
            line, self._from_lang, self._to_lang, extra
        ).translated_text
        output = oneline_text(translated) if self._oneline else translated
        self._remember(line, output)
        return output

    def _answer(self, question: str, extra: str | None) -> str:
        if not question:
            raise YakError("? の後に質問を入力してください")
        if not isinstance(self._backend, QuestionAnswerer):
            raise YakError("this backend does not support question mode")
        answer = self._backend.ask(question, self._context_text(), extra).answer
        output = oneline_text(answer) if self._oneline else answer
        self._remember(f"? {question}", output)
        return output

    def _remember(self, user_input: str, output: str) -> None:
        self._context.append((user_input, output))
        del self._context[:-MAX_CONTEXT_ENTRIES]

    def _context_text(self) -> str | None:
        if not self._context:
            return None
        return "\n\n".join(
            f"Input: {user_input}\nOutput: {output}"
            for user_input, output in self._context
        )

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
