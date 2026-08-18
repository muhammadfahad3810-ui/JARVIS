import inspect

import ai_tools
import intent_parser


# ---------------------------------------------------------------------
# Structural safety - proven, not just asserted (same discipline
# multilingual_normalizer.py's own structural-purity tests already use).
# ---------------------------------------------------------------------

def test_module_imports_no_control_module_no_voice_no_execution_primitive():
    """ai_tools.py must be pure: it can never execute anything, even in
    principle - no control module, no voice, no subprocess/os/ctypes/
    eval/exec."""

    source = inspect.getsource(ai_tools)

    forbidden = (
        "import subprocess", "import os", "import ctypes", "import voice",
        "import web_control", "import system_control", "import window_control",
        "import volume_control", "import media_control", "import screen_control",
        "import keyboard_control", "import mouse_control", "import input_control",
        "eval(", "exec(",
    )

    for token in forbidden:
        assert token not in source, f"ai_tools.py must never contain {token!r}"


def test_no_tool_can_render_a_dangerous_command():
    """Exhaustive sweep: no tool, with any combination of its allowed
    argument values, can ever render one of commands.DANGEROUS_COMMANDS.
    This is the direct proof for Task 7's/the module docstring's claim,
    not just an assertion of it."""

    import itertools

    dangerous = ("lock computer", "shutdown computer", "restart computer")

    for name, spec in ai_tools.TOOL_REGISTRY.items():

        # Build every combination of allowed values for this tool's
        # arguments (FREE_TEXT args are probed with a fixed, harmless
        # sample string - their whole point is being unconstrained, so
        # only the enum-constrained tools need exhaustive coverage).
        value_options = []

        for allowed in spec.args.values():
            if allowed is ai_tools.FREE_TEXT:
                value_options.append(["sample query"])
            else:
                value_options.append(sorted(allowed))

        arg_names = list(spec.args.keys())

        for combo in itertools.product(*value_options) if value_options else [()]:
            kwargs = dict(zip(arg_names, combo))
            rendered = spec.render(**kwargs)
            assert rendered not in dangerous, (
                f"tool {name!r} with args {kwargs!r} rendered a dangerous "
                f"command: {rendered!r}"
            )


def test_press_key_enum_never_includes_delete():
    assert "delete" not in ai_tools.TOOL_REGISTRY["press_key"].args["key"]
    assert "del" not in ai_tools.TOOL_REGISTRY["press_key"].args["key"]


def test_press_key_enum_is_exactly_known_keys():
    assert ai_tools.TOOL_REGISTRY["press_key"].args["key"] == frozenset(
        intent_parser.KNOWN_KEYS
    )


def test_open_application_enum_is_exactly_known_applications():
    assert ai_tools.TOOL_REGISTRY["open_application"].args["application"] == frozenset(
        intent_parser.KNOWN_APPLICATIONS.keys()
    )


def test_only_search_uses_free_text():
    """Confirms FREE_TEXT is used exactly once, for search's `query` -
    every other tool's arguments are closed enums."""

    free_text_tools = [
        name
        for name, spec in ai_tools.TOOL_REGISTRY.items()
        for allowed in spec.args.values()
        if allowed is ai_tools.FREE_TEXT
    ]

    assert free_text_tools == ["search"]


# ---------------------------------------------------------------------
# parse_tool_call() - shape validation (Task 1)
# ---------------------------------------------------------------------

def test_parse_valid_tool_call():
    tool_name, arguments = ai_tools.parse_tool_call(
        {"tool": "scroll", "arguments": {"direction": "down"}}
    )
    assert tool_name == "scroll"
    assert arguments == {"direction": "down"}


def test_parse_missing_arguments_defaults_to_empty_dict():
    tool_name, arguments = ai_tools.parse_tool_call({"tool": "refresh"})
    assert tool_name == "refresh"
    assert arguments == {}


def test_parse_rejects_non_dict_raw():
    for raw in ["scroll down", ["scroll", "down"], 42, None, 3.14]:
        try:
            ai_tools.parse_tool_call(raw)
            assert False, f"expected rejection for {raw!r}"
        except ai_tools.MalformedToolCallError:
            pass


def test_parse_rejects_missing_tool_field():
    try:
        ai_tools.parse_tool_call({"arguments": {"direction": "down"}})
        assert False, "expected rejection"
    except ai_tools.MalformedToolCallError:
        pass


def test_parse_rejects_non_string_tool_name():
    for bad_name in [123, None, ["scroll"], {"nested": "scroll"}]:
        try:
            ai_tools.parse_tool_call({"tool": bad_name})
            assert False, f"expected rejection for tool={bad_name!r}"
        except ai_tools.MalformedToolCallError:
            pass


def test_parse_rejects_non_dict_arguments():
    for bad_args in ["down", ["down"], 5]:
        try:
            ai_tools.parse_tool_call({"tool": "scroll", "arguments": bad_args})
            assert False, f"expected rejection for arguments={bad_args!r}"
        except ai_tools.MalformedToolCallError:
            pass


# ---------------------------------------------------------------------
# validate_tool_call() - the allow-list boundary (Task 1 / Task 8)
# ---------------------------------------------------------------------

def test_validate_unknown_tool_is_rejected():
    try:
        ai_tools.validate_tool_call("shutdown", {})
        assert False, "expected UnknownToolError"
    except ai_tools.UnknownToolError:
        pass


def test_validate_unknown_argument_is_rejected():
    try:
        ai_tools.validate_tool_call("scroll", {"direction": "down", "speed": "fast"})
        assert False, "expected UnknownArgumentError"
    except ai_tools.UnknownArgumentError:
        pass


def test_validate_wrong_argument_type_is_rejected():
    for bad_value in [1, 3.14, True, None, ["down"], {"nested": "down"}]:
        try:
            ai_tools.validate_tool_call("scroll", {"direction": bad_value})
            assert False, f"expected rejection for direction={bad_value!r}"
        except ai_tools.InvalidArgumentTypeError:
            pass


def test_validate_invalid_enum_value_is_rejected():
    try:
        ai_tools.validate_tool_call("scroll", {"direction": "sideways"})
        assert False, "expected InvalidArgumentValueError"
    except ai_tools.InvalidArgumentValueError:
        pass


def test_validate_invalid_application_is_rejected():
    try:
        ai_tools.validate_tool_call("open_application", {"application": "malware.exe"})
        assert False, "expected InvalidArgumentValueError"
    except ai_tools.InvalidArgumentValueError:
        pass


def test_validate_invalid_key_is_rejected():
    try:
        ai_tools.validate_tool_call("press_key", {"key": "delete"})
        assert False, "expected InvalidArgumentValueError"
    except ai_tools.InvalidArgumentValueError:
        pass


def test_validate_missing_required_argument_is_rejected():
    try:
        ai_tools.validate_tool_call("scroll", {})
        assert False, "expected MissingArgumentError"
    except ai_tools.MissingArgumentError:
        pass


def test_validate_extra_argument_is_rejected():
    try:
        ai_tools.validate_tool_call(
            "open_application", {"application": "chrome", "unexpected": "value"}
        )
        assert False, "expected UnknownArgumentError"
    except ai_tools.UnknownArgumentError:
        pass


def test_validate_nested_unexpected_object_is_rejected():
    try:
        ai_tools.validate_tool_call(
            "open_application", {"application": {"nested": "chrome"}}
        )
        assert False, "expected InvalidArgumentTypeError"
    except ai_tools.InvalidArgumentTypeError:
        pass


def test_validate_non_dict_arguments_is_rejected():
    try:
        ai_tools.validate_tool_call("scroll", "down")
        assert False, "expected rejection"
    except ai_tools.ToolContractError:
        pass


# ---- hostile/malformed argument sweep (Task 8) ----

_HOSTILE_APPLICATION_VALUES = (
    "cmd.exe & del /f /s /q C:\\*",
    "powershell -Command \"Remove-Item -Recurse C:\\\"",
    "python -c \"import os; os.system('rm -rf /')\"",
    "../../../../windows/system32",
    "$(whoami)",
    "`whoami`",
    "; rm -rf /",
    "http://evil.example.com/payload.exe",
)


def test_hostile_application_values_are_all_rejected():
    for value in _HOSTILE_APPLICATION_VALUES:
        try:
            ai_tools.validate_tool_call("open_application", {"application": value})
            assert False, f"expected rejection for application={value!r}"
        except ai_tools.InvalidArgumentValueError:
            pass


def test_hostile_key_values_are_all_rejected():
    for value in ("delete", "del", "windows", "F4 alt", "ctrl+alt+delete"):
        try:
            ai_tools.validate_tool_call("press_key", {"key": value})
            assert False, f"expected rejection for key={value!r}"
        except ai_tools.InvalidArgumentValueError:
            pass


def test_dangerous_action_tool_names_are_all_unknown():
    for name in (
        "delete", "shutdown", "restart", "lock", "shutdown_computer",
        "restart_computer", "lock_computer", "run_shell", "run_powershell",
        "execute_python", "exec", "eval", "os_system", "subprocess_run",
    ):
        try:
            ai_tools.validate_tool_call(name, {})
            assert False, f"expected UnknownToolError for tool={name!r}"
        except ai_tools.UnknownToolError:
            pass


# ---------------------------------------------------------------------
# resolve_to_canonical_command() - renders EXACTLY the strings the
# existing dispatch chain already expects (Task 4)
# ---------------------------------------------------------------------

def test_resolve_open_application_matches_existing_canonical_string():
    validated = ai_tools.validate_tool_call("open_application", {"application": "chrome"})
    assert ai_tools.resolve_to_canonical_command(validated) == "open chrome"
    assert (
        ai_tools.resolve_to_canonical_command(validated)
        == intent_parser.KNOWN_APPLICATIONS["chrome"]
    )


def test_resolve_press_key_matches_existing_canonical_string():
    validated = ai_tools.validate_tool_call("press_key", {"key": "enter"})
    assert ai_tools.resolve_to_canonical_command(validated) == "press enter"


def test_resolve_scroll_matches_existing_canonical_string():
    validated = ai_tools.validate_tool_call("scroll", {"direction": "down"})
    assert ai_tools.resolve_to_canonical_command(validated) == "scroll down"


def test_resolve_mouse_action_matches_existing_canonical_strings():
    cases = {
        "click": "click",
        "double_click": "double click",
        "right_click": "right click",
        "move_left": "move left",
        "move_right": "move right",
        "move_up": "move up",
        "move_down": "move down",
    }
    for action, expected in cases.items():
        validated = ai_tools.validate_tool_call("mouse_action", {"action": action})
        assert ai_tools.resolve_to_canonical_command(validated) == expected


def test_resolve_volume_matches_existing_canonical_strings():
    cases = {"up": "volume up", "down": "volume down", "mute": "mute", "unmute": "unmute"}
    for action, expected in cases.items():
        validated = ai_tools.validate_tool_call("volume", {"action": action})
        assert ai_tools.resolve_to_canonical_command(validated) == expected


def test_resolve_media_matches_existing_canonical_strings():
    cases = {
        "play_pause": "play",
        "next_track": "next track",
        "previous_track": "previous track",
    }
    for action, expected in cases.items():
        validated = ai_tools.validate_tool_call("media", {"action": action})
        assert ai_tools.resolve_to_canonical_command(validated) == expected


def test_resolve_tab_navigation_matches_existing_canonical_strings():
    validated = ai_tools.validate_tool_call("tab_navigation", {"direction": "next"})
    assert ai_tools.resolve_to_canonical_command(validated) == "next tab"

    validated = ai_tools.validate_tool_call("tab_navigation", {"direction": "previous"})
    assert ai_tools.resolve_to_canonical_command(validated) == "previous tab"


def test_resolve_browser_navigation_matches_existing_canonical_strings():
    validated = ai_tools.validate_tool_call("browser_navigation", {"direction": "back"})
    assert ai_tools.resolve_to_canonical_command(validated) == "go back"

    validated = ai_tools.validate_tool_call("browser_navigation", {"direction": "forward"})
    assert ai_tools.resolve_to_canonical_command(validated) == "go forward"


def test_resolve_refresh_matches_existing_canonical_string():
    validated = ai_tools.validate_tool_call("refresh", {})
    assert ai_tools.resolve_to_canonical_command(validated) == "refresh"


def test_resolve_search_matches_existing_canonical_prefix():
    validated = ai_tools.validate_tool_call("search", {"query": "python tutorials"})
    assert (
        ai_tools.resolve_to_canonical_command(validated)
        == "search for python tutorials"
    )


# ---------------------------------------------------------------------
# process_tool_call() - the composed, one-obvious-path convenience
# ---------------------------------------------------------------------

def test_process_tool_call_end_to_end_valid():
    result = ai_tools.process_tool_call(
        {"tool": "scroll", "arguments": {"direction": "down"}}
    )
    assert result == "scroll down"


def test_process_tool_call_end_to_end_invalid_enum_is_rejected():
    try:
        ai_tools.process_tool_call(
            {"tool": "scroll", "arguments": {"direction": "diagonal"}}
        )
        assert False, "expected rejection"
    except ai_tools.InvalidArgumentValueError:
        pass


def test_process_tool_call_end_to_end_unknown_tool_is_rejected():
    try:
        ai_tools.process_tool_call({"tool": "delete_everything", "arguments": {}})
        assert False, "expected rejection"
    except ai_tools.UnknownToolError:
        pass


def test_process_tool_call_end_to_end_malformed_raw_is_rejected():
    try:
        ai_tools.process_tool_call("not even an object")
        assert False, "expected rejection"
    except ai_tools.MalformedToolCallError:
        pass


# ---------------------------------------------------------------------
# Task 3: search safety - free-form query never treated as executable
# ---------------------------------------------------------------------

_SHELL_LOOKING_QUERIES = (
    "; rm -rf / #",
    "$(whoami)",
    "`cat /etc/passwd`",
    "&& del /f /s /q C:\\*",
    "| powershell -Command Remove-Item",
    "python -c \"import os; os.system('shutdown -h now')\"",
    "<script>alert(1)</script>",
    "../../etc/passwd",
)


def test_search_accepts_shell_looking_queries_as_plain_text():
    """Task 8: 'valid search query containing shell-looking text ->
    treated only as URL-encoded search text, never executed'. This
    proves process_tool_call() itself only ever produces a plain
    "search for <query>" STRING for these - never raises, never
    special-cases the content."""

    for query in _SHELL_LOOKING_QUERIES:
        result = ai_tools.process_tool_call(
            {"tool": "search", "arguments": {"query": query}}
        )
        assert result == f"search for {query}"
        assert isinstance(result, str)


def test_search_rejects_empty_query():
    try:
        ai_tools.validate_tool_call("search", {"query": ""})
        assert False, "expected rejection"
    except ai_tools.InvalidArgumentValueError:
        pass


def test_search_rejects_whitespace_only_query():
    try:
        ai_tools.validate_tool_call("search", {"query": "   "})
        assert False, "expected rejection"
    except ai_tools.InvalidArgumentValueError:
        pass


def test_search_rejects_non_string_query():
    for bad_query in [123, ["python"], {"q": "python"}, None]:
        try:
            ai_tools.validate_tool_call("search", {"query": bad_query})
            assert False, f"expected rejection for query={bad_query!r}"
        except ai_tools.InvalidArgumentTypeError:
            pass
