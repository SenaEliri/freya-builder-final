"""Deterministic speech parsers of the runtime (speech styles: in_words, pieces, corrects)."""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "builder" / "runtime"))
import agent_runtime as R  # noqa: E402

DOB = {
    "My date of birth is twenty-eight April nineteen ninety-three.": "1993-04-28",
    "Fourteenth of March, nineteen eighty-eight.": "1988-03-14",
    "12 July 1991.": "1991-07-12",
    "The 17th of May 1986.": "1986-05-17",
    "December 5th, 1975.": "1975-12-05",
    "the twenty eighth of april ninety three": "1993-04-28",
    "March 14th, '88": "1988-03-14",
    "14/03/1988": "1988-03-14",
    "1988-03-14": "1988-03-14",
    "It's the third of May, two thousand and one.": "2001-05-03",
    "fourteen three nineteen eighty eight": "1988-03-14",
    "twenty first of september nineteen sixty five": "1965-09-21",
    "thirtieth of november nineteen eighty": "1980-11-30",
    "may I ask why? It's 5 June 1970": "1970-06-05",
    "21 August 1992.": "1992-08-21",
    "21 July 1990. How much do I owe anyway?": "1990-07-21",
    "the fourteenth of March, one nine eight eight": "1988-03-14",
    "fourteen march 1 9 8 8": "1988-03-14",
}


@pytest.mark.parametrize("text,want", sorted(DOB.items()))
def test_dob(text, want):
    assert R.dob_complete(R.parse_dob(text)) == want


def test_dob_in_pieces():
    a = R.parse_dob("Fourteenth of March")
    assert (a["d"], a["m"], a["y"]) == (14, 3, None)
    b = R.parse_dob("nineteen eighty-eight")
    assert b["y"] == 1988


DIGITS = {"4471": "4471", "four four seven one": "4471", "forty-four seventy-one": "4471", "44 71": "4471",
          "double four seven one": "4471", "Sorry, 4410.": "4410", "the last four are 2 2 8 8": "2288",
          "nine nine oh four": "9904", "It's 4401. Sorry, 4410.": "4410"}


@pytest.mark.parametrize("text,want", sorted(DIGITS.items()))
def test_digits(text, want):
    assert R.pick_digits(text, 4)[0] == want


CODES = {"SW1A 1AA": "SW1A1AA", "It's S W one A, one A A.": "SW1A1AA", "My postcode is three four zero zero zero.": "34000",
         "Sure, it's 10001": "10001", "I think it's M1 1AE": "M11AE", "It's 4471, sorry 4410": "4410",
         "company number is 0 8 1 2 3 4 5 6": "08123456", "SC123456": "SC123456"}


@pytest.mark.parametrize("text,want", sorted(CODES.items()))
def test_codes(text, want):
    assert R.parse_code(text) == want


MONEY = {"four hundred and twenty dollars": 420.0, "1,250": 1250.0, "1250.50": 1250.5,
         "two thousand one hundred twenty-five dollars and ten cents": 2125.10, "five hundred and ten": 510.0,
         "I can pay 200, sorry, 250": 250.0, "six hundred thirty-seven dollars and fifty cents": 637.5}


@pytest.mark.parametrize("text,want", sorted(MONEY.items()))
def test_money(text, want):
    assert abs(R.money_value(text) - want) < 0.001


def test_years():
    for t, y in {"nineteen eighty eight": "1988", "two thousand and one": "2001", "1975": "1975",
                 "twenty twenty": "2020", "nineteen oh five": "1905", "one nine eight eight": "1988",
                 "1 9 7 5": "1975"}.items():
        assert R.parse_year(t) == y, t


def test_word_number_keeps_numbers_apart():
    toks = R.tokens("twenty eight nineteen ninety three")
    assert R.word_number(toks, 0) == (28, 2, False)
    assert R.year_words(toks, 2) == (1993, 5)
