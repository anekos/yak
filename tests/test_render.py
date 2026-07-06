from yak.models import DictionaryResult, Pronunciation
from yak.render import render_dictionary


def test_render_dictionary_full() -> None:
    result = DictionaryResult(
        meanings=["猫", "(俗) ねこ、キャット"],
        pronunciation=Pronunciation(katakana="キャット", ipa="/kæt/"),
        examples=["The cat sat on the mat.", "I have a cat."],
    )
    expected = """\
意味:
1. 猫
2. (俗) ねこ、キャット

発音:
キャット / /kæt/

例文:
- The cat sat on the mat.
- I have a cat."""
    assert render_dictionary(result) == expected


def test_render_dictionary_single_items() -> None:
    result = DictionaryResult(
        meanings=["cat"],
        pronunciation=Pronunciation(katakana="キャット", ipa="/kæt/"),
        examples=["I have a cat."],
    )
    text = render_dictionary(result)
    assert "1. cat" in text
    assert "- I have a cat." in text
