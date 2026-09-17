"""Tests for the parsers that read a verdict out of an AI reply.

These run on strings only -- no provider is contacted -- so they are the cheap
place to pin down how tolerant the parsing has to be. All four providers share
plainbook.ai_common.parse_validation_response, so a shape fixed here is fixed
everywhere.
"""

import pytest
from plainbook.ai_common import parse_validation_response


# Shapes that must read as approval. The prompt asks for a bare "YES", but
# models wrap it in markdown, quote it, or continue straight into a sentence.
VALID_RESPONSES = [
    "YES\n\nLooks right.",
    # Verbatim from a Claude validation stored in
    # test_notebooks/User_study_modification_amended.plnb, which used to be
    # shown to the user in a red "invalid" bar.
    '**YES**\n\nThe cell correctly implements the requested "win balance" dataset:\n\n'
    "- It iterates over all matches and accumulates, per country, the total number "
    "of matches played.",
    "*YES* the code is fine",
    "__YES__\n\nfine",
    "`YES`\n\nfine",
    "## YES\n\nfine",
    "> YES\n\nfine",
    "- YES\n\nfine",
    '"YES"\n\nfine',
    "(YES)\n\nfine",
    "\n\n  **YES**  \n\nfine",
    "Yes, the code matches the description.",
    "yes. it works",
    "YES: the code is correct",
    # The parser skips every leading non-letter rather than listing the ones it
    # expects, so decorations nobody anticipated are read correctly too.
    "\u2705 YES\n\nfine",
    "1. YES\n\nfine",
    "=== YES ===\n\nfine",
    "**_`YES`_**\n\nfine",
    "[YES]\n\nfine",
    "\u3010YES\u3011\n\nfine",
    "***YES***\n\nfine",
    # Any casing, decorated or not: the pattern is IGNORECASE and both the
    # leading skip and the trailing guard exclude letters of either case.
    "yes\n\nlooks right",
    "yEs\n\nlooks right",
    "**yes**\n\nlooks right",
    "__yes__\n\nfine",
    "## Yes\n\nfine",
]

# Shapes that must read as rejection.
INVALID_RESPONSES = [
    "NO\n\nIt drops the ties column.",
    "**NO**\n\nIt drops the ties column.",
    "no - it forgets the header",
    "## NO\n\nwrong columns",
    '"NO"\n\nwrong',
    "no\n\nit drops the ties column",
    "nO\n\nit drops the ties column",
    "**no**\n\nit drops the ties column",
    "> No\n\nit drops the ties column",
]

# Replies carrying no verdict at all. These must fail closed -- an unreviewed
# cell must never look approved -- and must say the verdict was unreadable, so a
# red bar over approving-sounding text is at least explained. The first four
# would each be read as a NO by a plain startswith("NO").
UNPARSEABLE_RESPONSES = [
    "NOTE: the code is correct and complete.",
    "Nothing is wrong with this cell.",
    "None of the requirements are missed.",
    "Not sure, the description is ambiguous.",
    # Lowercase too: the separator guard must not be case-sensitive, or these
    # slip through as verdicts.
    "note: the code is correct",
    "nothing is wrong here",
    "none of the requirements are missed",
    "yesterday this worked",
    "The code is correct and there is no error anywhere.",
    "I have reviewed the cell.",
    "",
    "   \n\n  ",
    None,
]


@pytest.mark.parametrize("text", VALID_RESPONSES)
def test_validation_yes(text):
    result = parse_validation_response(text)
    assert result["is_valid"] is True


@pytest.mark.parametrize("text", INVALID_RESPONSES)
def test_validation_no(text):
    result = parse_validation_response(text)
    assert result["is_valid"] is False
    # A real rejection must not be reported as an unreadable one.
    assert "could not be read" not in result["message"]


@pytest.mark.parametrize("text", UNPARSEABLE_RESPONSES)
def test_validation_without_a_verdict_fails_closed(text):
    result = parse_validation_response(text)
    assert result["is_valid"] is False
    assert "could not be read" in result["message"]


@pytest.mark.parametrize("text", VALID_RESPONSES + INVALID_RESPONSES)
def test_verdict_is_kept_in_the_message(text):
    """The reply is shown as the model wrote it, verdict included.

    The verdict decides is_valid; it is deliberately not excised, so the user
    can see what the model actually answered."""
    assert parse_validation_response(text)["message"] == text.strip()


def test_message_is_the_reply_verbatim():
    """Nothing is trimmed from the reply but surrounding whitespace."""
    reply = "**NO**\n\nIt drops the `Ties` column:\n\n- no groupby"
    result = parse_validation_response(reply)
    assert result["is_valid"] is False
    assert result["message"] == reply


def test_bulleted_body_keeps_its_first_bullet():
    """A list opening the explanation is untouched, bullet included."""
    reply = "**YES**\n\n- It iterates over all matches\n- It builds the frame"
    result = parse_validation_response(reply)
    assert result["is_valid"] is True
    assert result["message"] == reply


def test_digits_opening_the_explanation_survive():
    reply = "YES. 3 columns are built as asked."
    result = parse_validation_response(reply)
    assert result["is_valid"] is True
    assert result["message"] == reply


def test_unparseable_reply_is_quoted_in_full():
    reply = "I have reviewed the cell and it looks fine to me."
    result = parse_validation_response(reply)
    assert result["is_valid"] is False
    assert result["message"].endswith(reply)
