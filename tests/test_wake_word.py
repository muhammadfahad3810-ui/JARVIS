import jarvis


# ---------------------------------------------------------------------
# extract_command_after_wake_word()
# ---------------------------------------------------------------------

def test_wake_word_alone_returns_empty_string():
    assert jarvis.extract_command_after_wake_word("jarvis") == ""


def test_wake_word_with_command():
    assert jarvis.extract_command_after_wake_word(
        "jarvis open chrome"
    ) == "open chrome"


def test_wake_word_anywhere_in_phrase():
    assert jarvis.extract_command_after_wake_word(
        "hey jarvis open chrome"
    ) == "open chrome"


def test_doubled_wake_word_is_handled_gracefully():
    assert jarvis.extract_command_after_wake_word(
        "jarvis jarvis open chrome"
    ) == "open chrome"


def test_tripled_wake_word_is_handled_gracefully():
    assert jarvis.extract_command_after_wake_word(
        "jarvis jarvis jarvis open chrome"
    ) == "open chrome"


def test_no_wake_word_returns_none():
    assert jarvis.extract_command_after_wake_word("open chrome") is None


# ---------------------------------------------------------------------
# Wake-word variations (Phase 4)
# ---------------------------------------------------------------------

def test_jervis_alias_is_recognized():
    assert jarvis.extract_command_after_wake_word(
        "jervis open chrome"
    ) == "open chrome"


def test_possessive_jarviss_is_recognized():
    assert jarvis.extract_command_after_wake_word(
        "jarvis's open chrome"
    ) == "open chrome"


def test_repeated_jervis_alias_is_handled():
    assert jarvis.extract_command_after_wake_word(
        "jervis jervis open chrome"
    ) == "open chrome"


def test_mixed_alias_and_canonical_repeat_is_handled():
    assert jarvis.extract_command_after_wake_word(
        "jarvis jervis open chrome"
    ) == "open chrome"


def test_word_that_merely_contains_wake_word_does_not_match():
    """'jarvison' contains 'jarvis' as a substring but is not the wake
    word - word-boundary matching must reject it."""
    assert jarvis.extract_command_after_wake_word(
        "jarvison is not a real word"
    ) is None


def test_word_ending_in_wake_word_does_not_match():
    assert jarvis.extract_command_after_wake_word(
        "myjarvis open chrome"
    ) is None


# ---------------------------------------------------------------------
# contains_wake_word()
# ---------------------------------------------------------------------

def test_contains_wake_word_true_for_canonical():
    assert jarvis.contains_wake_word("jarvis open chrome") is True


def test_contains_wake_word_true_for_alias():
    assert jarvis.contains_wake_word("jervis open chrome") is True


def test_contains_wake_word_false_when_absent():
    assert jarvis.contains_wake_word("open chrome") is False


def test_contains_wake_word_false_for_substring_word():
    assert jarvis.contains_wake_word("jarvison opens things") is False
