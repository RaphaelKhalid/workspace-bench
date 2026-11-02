"""banks.native_langs (plan 0032 §2.10): the subject's native languages, from the bank header."""

import pytest

from wsbench import banks


def test_native_langs_default_and_header():
    assert banks.native_langs({}) == ("en", "zh")
    assert banks.native_langs({"contract": {"native_langs": ["en", "ja"]}}) == ("en", "ja")
    with pytest.raises(ValueError):
        banks.native_langs({"contract": {"native_langs": ["zh", "en"]}})
