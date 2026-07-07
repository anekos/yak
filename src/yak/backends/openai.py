from openai import OpenAI, OpenAIError
from pydantic import BaseModel

from yak.errors import YakError
from yak.models import DictionaryResult, ModeDecision, TranslationResult

DEFAULT_MODEL = "gpt-5-mini"
DEFAULT_CLASSIFIER_MODEL = "gpt-5-nano"


def language_instruction(from_lang: str | None, to_lang: str | None) -> str:
    """--from/--to の指定状況から言語決定の指示文を組み立てる。

    未指定時は英日ペアとみなし、原文と逆の言語へ翻訳する(spec の言語決定ルール)。
    """
    if from_lang and to_lang:
        return f"Translate the text from {from_lang} to {to_lang}."
    if to_lang:
        return f"Detect the language of the text and translate it to {to_lang}."
    if from_lang:
        return (
            f"The text is in {from_lang}. "
            "If that language is English, translate to Japanese; "
            "if it is Japanese, translate to English; "
            "otherwise translate to Japanese."
        )
    return (
        "Detect the language of the text. "
        "If it is Japanese, translate to English; otherwise translate to Japanese."
    )


_TRANSLATE_SYSTEM = (
    "You are a translation engine. {languages} "
    "Preserve the meaning, tone, and register of the original text. "
    "Set detected_source_language to the language of the input text."
)

_DICTIONARY_SYSTEM = (
    "You are a bilingual dictionary. {languages} "
    "The input is a word or short phrase. Respond with: "
    "meanings — the senses of the input translated into the target language, "
    "with register or nuance notes where relevant; "
    "pronunciation — katakana reading and IPA; "
    "examples — a few example sentences. "
    "For pronunciation and examples, use the non-Japanese side of the pair: "
    "if the input is Japanese, use the translated word; "
    "otherwise use the input word itself."
)

_CLASSIFY_SYSTEM = (
    "You are a mode classifier for a translation tool. "
    "Decide whether the input is a dictionary headword: a single word, or a "
    "short set phrase that belongs in a dictionary as an entry, such as an "
    "idiom, phrasal verb, or compound (e.g. 'look up', 'in spite of', '猫'). "
    "Sentences and free-form text are not dictionary headwords. "
    "The input may be in any language."
)


class OpenAIBackend:
    """Translator / DictionaryProvider の OpenAI 実装。"""

    def __init__(self, client: OpenAI, model: str) -> None:
        self._client = client
        self._model = model

    def translate(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> TranslationResult:
        system = _TRANSLATE_SYSTEM.format(
            languages=language_instruction(from_lang, to_lang)
        )
        return self._parse(system, text, extra_instruction, TranslationResult)

    def lookup(
        self,
        text: str,
        from_lang: str | None,
        to_lang: str | None,
        extra_instruction: str | None,
    ) -> DictionaryResult:
        system = _DICTIONARY_SYSTEM.format(
            languages=language_instruction(from_lang, to_lang)
        )
        return self._parse(system, text, extra_instruction, DictionaryResult)

    def classify(self, text: str) -> ModeDecision:
        return self._parse(_CLASSIFY_SYSTEM, text, None, ModeDecision)

    def _parse[T: BaseModel](
        self,
        system: str,
        text: str,
        extra_instruction: str | None,
        response_format: type[T],
    ) -> T:
        if extra_instruction:
            system = f"{system}\n\nAdditional instructions:\n{extra_instruction}"
        try:
            completion = self._client.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                response_format=response_format,
            )
        except OpenAIError as e:
            raise YakError(f"OpenAI API error: {e}") from e
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise YakError("OpenAI returned an empty response")
        return parsed
