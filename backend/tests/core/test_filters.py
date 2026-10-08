import pytest

from apps.core.exceptions import Invalid
from apps.core.filters import parse_choice

CHOICES = ("cost", "take_home")


def test_a_choice_is_read_in_any_case():
    assert parse_choice(" Take_Home ", name="view", choices=CHOICES) == "take_home"


def test_nothing_given_is_the_default_or_a_400_without_one():
    assert parse_choice("", name="view", choices=CHOICES, default="cost") == "cost"
    with pytest.raises(Invalid) as excinfo:
        parse_choice(None, name="view", choices=CHOICES)

    assert excinfo.value.errors == {"view": ["view must be cost or take_home"]}


def test_anything_else_is_a_400_that_lists_the_choices():
    with pytest.raises(Invalid) as excinfo:
        parse_choice("net", name="view", choices=CHOICES, default="cost")

    assert excinfo.value.errors == {"view": ["view must be cost or take_home, got net"]}
