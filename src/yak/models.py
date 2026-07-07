from pydantic import BaseModel


class TranslationResult(BaseModel):
    """通常翻訳の結果。OpenAI Structured Outputs のスキーマとしても使う。"""

    detected_source_language: str
    translated_text: str


class Pronunciation(BaseModel):
    katakana: str
    ipa: str


class DictionaryResult(BaseModel):
    """辞書モードの結果。OpenAI Structured Outputs のスキーマとしても使う。"""

    meanings: list[str]
    pronunciation: Pronunciation
    examples: list[str]


class ModeDecision(BaseModel):
    """モード自動判定の結果。OpenAI Structured Outputs のスキーマとしても使う。"""

    is_dictionary_entry: bool
