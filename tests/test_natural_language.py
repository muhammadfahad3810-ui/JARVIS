import natural_language


# ---------------------------------------------------------------------
# Valid splits - every clause independently resolves to a known command
# ---------------------------------------------------------------------

def test_splits_two_known_clauses_on_and():
    result = natural_language.split_into_clauses(
        "open chrome and search for python"
    )
    assert result == ["open chrome", "search for python"]


def test_splits_two_known_clauses_on_then():
    result = natural_language.split_into_clauses(
        "open chrome then search for python"
    )
    assert result == ["open chrome", "search for python"]


def test_splits_three_known_clauses():
    result = natural_language.split_into_clauses(
        "open chrome and open notepad and mute"
    )
    assert result == ["open chrome", "open notepad", "mute"]


def test_splits_clauses_spanning_different_modules():
    result = natural_language.split_into_clauses("open notepad and mute")
    assert result == ["open notepad", "mute"]


# ---------------------------------------------------------------------
# All-or-nothing safety: if ANY clause doesn't resolve, do not split
# ---------------------------------------------------------------------

def test_does_not_split_bed_and_breakfast():
    """'breakfast' alone is not a known command, so the split must be
    discarded entirely - the original text is returned as a single
    clause, which is itself a valid, unaffected SEARCH command."""
    result = natural_language.split_into_clauses(
        "search for bed and breakfast"
    )
    assert result == ["search for bed and breakfast"]


def test_does_not_split_when_second_clause_is_ambiguous():
    result = natural_language.split_into_clauses(
        "do something and open chrome"
    )
    assert result == ["do something and open chrome"]


def test_does_not_split_dangerous_looking_clause():
    """A dangerous-sounding second clause with no known command mapping
    must never be split out and independently processed."""
    result = natural_language.split_into_clauses(
        "open chrome and delete everything"
    )
    assert result == ["open chrome and delete everything"]


def test_does_not_split_exit_chain():
    """Documented limitation: intent_parser.classify() doesn't cover
    exit words, so a chain ending in 'exit' fails closed (no split)
    rather than being guessed at."""
    result = natural_language.split_into_clauses("open chrome and exit")
    assert result == ["open chrome and exit"]


# ---------------------------------------------------------------------
# No-op cases
# ---------------------------------------------------------------------

def test_single_command_is_not_split():
    result = natural_language.split_into_clauses("mute")
    assert result == ["mute"]


def test_empty_string_returns_itself():
    result = natural_language.split_into_clauses("")
    assert result == [""]


def test_no_conjunction_present_returns_original_text_unmodified():
    text = "please open chrome for me"
    result = natural_language.split_into_clauses(text)
    assert result == [text]


# ---------------------------------------------------------------------
# Security: this module never executes anything itself
# ---------------------------------------------------------------------

def test_module_imports_no_execution_capable_dependency():
    """Structural guarantee: natural_language.py must only ever import
    command_parser/intent_parser (both pure, side-effect-free) - never
    subprocess, os, ctypes, comtypes, or any action module directly."""

    import inspect

    source = inspect.getsource(natural_language)

    forbidden = [
        "import subprocess",
        "import os",
        "import ctypes",
        "import comtypes",
        "import system_control",
        "import window_control",
        "import volume_control",
        "import audio_endpoint",
        "import web_control",
        "import keyboard_control",
        "import input_control",
    ]

    for forbidden_import in forbidden:
        assert forbidden_import not in source, forbidden_import


def test_split_into_clauses_is_pure_no_side_effects():
    """Calling split_into_clauses() must never itself trigger any real
    action - it only classifies, never dispatches. Proven by mocking
    every real action primitive and confirming none are touched purely
    by calling this function directly (not through CommandProcessor)."""

    from unittest.mock import patch

    with patch("system_control.subprocess.Popen") as mock_popen, \
         patch("system_control.os.system") as mock_system, \
         patch("volume_control.audio_endpoint.set_mute") as mock_mute, \
         patch(
             "volume_control.audio_endpoint.set_volume_percent"
         ) as mock_vol, \
         patch("web_control.webbrowser.open") as mock_open:
        natural_language.split_into_clauses(
            "open chrome and mute and shutdown computer"
        )

    mock_popen.assert_not_called()
    mock_system.assert_not_called()
    mock_mute.assert_not_called()
    mock_vol.assert_not_called()
    mock_open.assert_not_called()
