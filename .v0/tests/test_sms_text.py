import unicodedata

import pytest

from gsm_agent.domain.sms_text import ReplyLimits, plan_sms, single_sms_capacity, sms_encoding, sms_units
from gsm_agent.infra.text.plain_text import PlainTextNormalizer


def test_markdown_to_plain_text_preserves_links_code_and_arabic():
    text = (
        "# Greeting\n\n**مرحبا**! *Hello*.\n\n- [Site](https://example.com)\n"
        "- `a_b`\n\n```python\nprint(1)\n```"
    )
    result = PlainTextNormalizer().normalize(text)
    assert "مرحبا! Hello." in result
    assert "Site (https://example.com)" in result
    assert "a_b" in result
    assert "print(1)" in result
    assert "**" not in result and "```" not in result and "# " not in result
    assert "- " not in result


def test_normalization_reduces_encoding_cost_without_destroying_prose():
    result = PlainTextNormalizer().normalize("I’m “fine”—really… 😀\u200b\n\n3 * 4 = 12; foo_bar_baz")
    assert result == 'I\'m "fine"-really...\n\n3 * 4 = 12; foo_bar_baz'
    assert sms_encoding(result) == "GSM7_default"
    assert PlainTextNormalizer().normalize(result) == result


def test_plain_text_tables_and_html():
    formatter = PlainTextNormalizer()
    assert "bold" in formatter.normalize("<b>bold</b>")
    table = formatter.normalize("| Key | Value |\n| --- | --- |\n| A | B |")
    assert "Key; Value" in table
    assert "---" not in table and "|" not in table


def test_split_prefers_paragraphs_sentences_and_words():
    text = "First paragraph. " * 5 + "\n\n" + "Second paragraph. " * 5
    plan = plan_sms(text, ReplyLimits(max_reply_chars=400, max_sms_parts=3))
    assert plan.parts[0] == "(1/2) " + ("First paragraph. " * 5).strip()
    assert plan.parts[1] == "(2/2) " + ("Second paragraph. " * 5).strip()
    sentences = plan_sms("A whole sentence. " * 20, ReplyLimits(400, 3))
    assert sentences.parts[0].endswith("sentence.")
    words = plan_sms("word " * 60, ReplyLimits(400, 3))
    assert words.parts[0].endswith("word")


@pytest.mark.parametrize("text", ["hello " * 100, "مرحبا " * 100, "€^[] " * 100, "x" * 500])
@pytest.mark.parametrize("parts", [1, 2, 3])
def test_character_and_physical_sms_caps_include_numbering(text, parts):
    limits = ReplyLimits(max_reply_chars=240, max_sms_parts=parts)
    plan = plan_sms(text, limits)
    assert len(plan.text) <= limits.max_reply_chars
    assert len(plan.parts) <= parts
    for part in plan.parts:
        assert sms_units(part) <= single_sms_capacity(sms_encoding(part))
    if len(plan.parts) > 1:
        assert all(part.startswith(f"({i}/{len(plan.parts)}) ") for i, part in enumerate(plan.parts, 1))
    # A second preparation must not change the persisted plan.
    assert plan_sms(plan.text, limits).parts == plan.parts


def test_extended_gsm_characters_and_unicode_boundaries():
    assert sms_units("^€[]") == 8
    assert len(plan_sms("^" * 80, ReplyLimits(240, 3)).parts) == 1
    assert len(plan_sms("^" * 81, ReplyLimits(240, 3)).parts) == 2
    assert len(plan_sms("ب" * 70, ReplyLimits(240, 3)).parts) == 1
    assert len(plan_sms("ب" * 71, ReplyLimits(240, 3)).parts) == 2
    text = "بَ" * 80
    for part in plan_sms(text, ReplyLimits(240, 3)).parts:
        assert not unicodedata.combining(part.split(" ", 1)[1][0])
