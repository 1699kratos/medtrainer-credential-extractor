import pytest

from judge import check_concise, count_sentences


@pytest.mark.parametrize(
    "text, n",
    [
        ("", 0),
        ("One sentence with no period", 1),
        ("A license issued to Jane Doe. It expires 12/31/2027.", 2),
        ("Issued to Robert Alan Mitchell Jr. by the Texas Board, license No. 123.", 1),  # abbreviations
        ("First. Second. Third.", 3),
        ("Is it valid? Yes. The date is printed as 03/31/2028.", 3),
    ],
)
def test_count_sentences(text, n):
    assert count_sentences(text) == n


def test_check_concise_limits():
    ok, _ = check_concise("Short one. Short two.")
    assert ok
    ok, _ = check_concise("One. Two. Three.")
    assert not ok
    ok, reason = check_concise("word " * 61)
    assert not ok and "61 words" in reason
