import pytest

from pydantic_views.metaclass import AccessTag


def test_access_tag_inmutable():
    tag1 = AccessTag("tag1")
    tag2 = AccessTag("tag2")

    assert tag1.name == "tag1"
    assert tag2.name == "tag2"

    with pytest.raises(TypeError):
        tag1.name = "new_name"  # type: ignore

    with pytest.raises(TypeError):
        tag2.name = "new_name"  # type: ignore


def test_access_tag_singleton():
    tag1a = AccessTag("tag1")
    tag1b = AccessTag("tag1")

    assert tag1a is tag1b
    assert tag1a == "tag1"
    assert tag1b == "tag1"


def test_access_tag_hashable():
    tag1 = AccessTag("tag1")
    tag2 = AccessTag("tag2")

    tag_set = {tag1, tag2}

    assert tag1 in tag_set
    assert tag2 in tag_set


def test_access_tag_repr():
    tag1 = AccessTag("tag1")
    tag2 = AccessTag("tag2")

    assert repr(tag1) == "AccessTag(tag1)"
    assert repr(tag2) == "AccessTag(tag2)"


def test_access_tag_equality():
    tag1a = AccessTag("tag1")
    tag1b = AccessTag("tag1")
    tag2 = AccessTag("tag2")

    assert tag1a == tag1b
    assert tag1a != tag2
    assert tag1b != tag2
