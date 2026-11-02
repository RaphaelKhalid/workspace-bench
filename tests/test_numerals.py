"""wsbench.numerals (plan 0032 §2.7.5a, chain.md C2's semantics): numerals in any language."""

from wsbench import digest, numerals


def test_numbers_in_multilingual():
    cases = {
        "七": 7,
        "十八": 18,
        "sieben": 7,
        "ocho": 8,
        "cinco": 5,
        "twenty-six": 26,
        "sechsundzwanzig": 26,
        "第十八": 18,
        "eighteenth": 18,
        "vingt-deux": 22,
        "vinte e seis": 26,
        "двадцать шесть": 26,
        "tweeëntwintig": 22,
        "ventotto": 28,
        "\uff11\uff12": 12,  # fullwidth digits
    }
    for text, v in cases.items():
        assert numerals.numbers_in(text) == {v}, text
        assert numerals.word_value(text) == v, text


def test_names_value_whole_number():
    for text in ("15", "2019", "10.5"):
        assert not numerals.names_value(5, text), text
    assert numerals.names_value(5, "the answer is 5.")
    assert numerals.names_value(1000, "1,000 people")
    assert numerals.names_value(18, "the result is eighteen")
    # an English homograph of a number word is not a number in running text
    assert not numerals.names_value(2, "the payment is due")
    assert numerals.word_value("due") == 2  # but it is one as a single key


def test_digest_word_key_grounds():
    assert digest.number_value("eight") == 8.0 and digest.number_value("sieben") == 7.0
    assert digest._number_key_ok("eight", "I get eight in the end")
    assert not digest._number_key_ok("eight", "eighteen")
