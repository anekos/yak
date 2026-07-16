from typing import Protocol, runtime_checkable

from yak.models import AnswerResult, DictionaryResult, ModeDecision, TranslationResult


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


@runtime_checkable
class QuestionAnswerer(Protocol):
    """質問モード(`? ...`)を提供できるバックエンドのインターフェイス。"""

    def ask(
        self,
        question: str,
        context: str | None,
        extra_instruction: str | None,
    ) -> AnswerResult: ...


@runtime_checkable
class ModeClassifier(Protocol):
    """入力が辞書の見出し語かどうかを判定するバックエンドのインターフェイス。"""

    def classify(self, text: str) -> ModeDecision: ...
