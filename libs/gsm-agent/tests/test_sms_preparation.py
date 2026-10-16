import unicodedata

import pytest
from gsm_agent.application.text import PlainTextNormalizer, SmsLimits, prepare_sms
from gsm_agent_core.domain.submission import SmsEncoding, SmsSendConstraints, sms_units

CONSTRAINTS = SmsSendConstraints()


def test_normalize_markdown_tables_links_code_html_and_arabic():
    text = (
        "# Heading\n\n**مرحبا**! *Hello*.\n\n- [Site](https://example.com)\n- `a_b`\n\n```py\nprint(1)\n```"
    )
    plain = PlainTextNormalizer().normalize(text)
    assert "مرحبا! Hello." in plain and "Site (https://example.com)" in plain
    assert "a_b" in plain and "print(1)" in plain
    assert all(marker not in plain for marker in ("**", "```", "# ", "- "))
    assert "bold" in PlainTextNormalizer().normalize("<b>bold</b>")
    table = PlainTextNormalizer().normalize("| Key | Value |\n| --- | --- |\n| A | B |")
    assert "Key; Value" in table and "---" not in table


def test_punctuation_and_plain_math_are_preserved_with_lower_encoding_cost():
    source = "I’m “fine”—really…\u200b\n\n3 * 4 = 12; foo_bar_baz"
    plain = PlainTextNormalizer().normalize(source)
    assert plain == 'I\'m "fine"-really...\n\n3 * 4 = 12; foo_bar_baz'
    assert PlainTextNormalizer().normalize(plain) == plain


def test_split_prefers_paragraphs_then_sentences_then_words():
    plan = prepare_sms(
        "First paragraph. " * 5 + "\n\n" + "Second paragraph. " * 5, SmsLimits(400, 3), CONSTRAINTS
    )
    assert plan.parts == (
        "(1/2) " + ("First paragraph. " * 5).strip(),
        "(2/2) " + ("Second paragraph. " * 5).strip(),
    )
    sentences = prepare_sms("A whole sentence. " * 20, SmsLimits(400, 3), CONSTRAINTS)
    assert sentences.parts[0].endswith("sentence.")
    words = prepare_sms("word " * 60, SmsLimits(400, 3), CONSTRAINTS)
    assert words.parts[0].endswith("word")


@pytest.mark.parametrize("text", ["hello " * 100, "مرحبا " * 100, "€^[] " * 100, "x" * 500, "بَ" * 100])
@pytest.mark.parametrize("parts", [1, 2, 3, 9])
def test_total_chars_numbering_encoding_and_part_limits(text, parts):
    limits = SmsLimits(240, parts)
    plan = prepare_sms(text, limits, CONSTRAINTS)
    assert 1 <= len(plan.parts) <= parts
    assert sum(map(len, plan.parts)) <= limits.max_total_chars
    for part in plan.parts:
        assert sms_units(part, plan.encoding) <= CONSTRAINTS.capacity(plan.encoding)
    assert plan.truncated


def test_gsm_extension_cost_and_unicode_clusters():
    assert sms_units("^€[]", SmsEncoding.GSM7) == 8
    assert len(prepare_sms("^" * 80, SmsLimits(), CONSTRAINTS).parts) == 1
    assert len(prepare_sms("^" * 81, SmsLimits(), CONSTRAINTS).parts) == 2
    assert len(prepare_sms("ب" * 70, SmsLimits(), CONSTRAINTS).parts) == 1
    assert len(prepare_sms("ب" * 71, SmsLimits(), CONSTRAINTS).parts) == 2
    plan = prepare_sms("بَ" * 80, SmsLimits(), CONSTRAINTS)
    for part in plan.parts:
        assert not unicodedata.combining(part.split(" ", 1)[1][0])


@pytest.mark.parametrize("text", ["", "   ", "😀 hello", "hello\ud800", "ب" + "َ" * 80])
def test_empty_unsupported_or_unbreakable_text_is_explicitly_rejected(text):
    with pytest.raises(ValueError):
        prepare_sms(text, SmsLimits(), CONSTRAINTS)


def test_adapter_constraints_and_visible_truncation():
    small = SmsSendConstraints(gsm7_units=40)
    plan = prepare_sms("A sentence. " * 30, SmsLimits(100, 2), small)
    assert len(plan.parts) == 2 and plan.parts[-1].endswith("...") and plan.truncated
    assert all(sms_units(part, plan.encoding) <= 40 for part in plan.parts)
    with pytest.raises(ValueError, match="unsupported"):
        prepare_sms("مرحبا", SmsLimits(), SmsSendConstraints(encodings=(SmsEncoding.GSM7,)))
    assert not prepare_sms("Hello...", SmsLimits(), CONSTRAINTS).truncated


def test_boundaries_do_not_detach_a_combining_mark_from_whitespace():
    text = "ب" * 55 + " \u0301" + "ب" * 55
    plan = prepare_sms(text, SmsLimits(240, 3), CONSTRAINTS)
    for part in plan.parts:
        body = part.split(" ", 1)[1]
        assert not unicodedata.combining(body[0])
