"""Tests for the consolidated chat tool surface.

The chat agent used to expose `respond_with_revision` as a parallel
response-mode tool alongside plain text. That was consolidated to a
single `respond` tool whose revision fields are optional. These tests
pin the new schema so regressions (e.g., accidentally making
`revised_sql` required again) are caught early.
"""

from agent.chat_tools import CHAT_TOOLS, RESPOND_ONLY_TOOLS, respond, run_query


def _tool_by_name(tools, name):
    for t in tools:
        if t.name == name:
            return t
    raise AssertionError(f"tool {name!r} not in {[t.name for t in tools]}")


def test_chat_tools_contains_run_query_and_respond():
    names = {t.name for t in CHAT_TOOLS}
    assert names == {"run_query", "respond"}


def test_respond_only_tools_is_just_respond():
    names = {t.name for t in RESPOND_ONLY_TOOLS}
    assert names == {"respond"}


def test_respond_schema_has_message_required_and_revision_optional():
    schema = respond.args_schema.model_json_schema()
    required = set(schema.get("required", []))
    props = schema.get("properties", {})
    assert required == {"message"}, \
        f"Only `message` should be required, got {required}"
    assert "revised_sql" in props and "explanation" in props
    # Optional fields must tolerate being omitted entirely.
    assert "revised_sql" not in required
    assert "explanation" not in required


def test_respond_is_callable_with_just_message():
    # Tool body is a no-op (execution happens in the agentic loop); this
    # just confirms the schema accepts a message-only invocation.
    respond.invoke({"message": "hi"})


def test_respond_accepts_full_revision_payload():
    respond.invoke({
        "message": "Here's a fix",
        "revised_sql": "SELECT 1",
        "explanation": "Added the missing column",
    })


def test_run_query_schema_is_unchanged():
    schema = run_query.args_schema.model_json_schema()
    assert set(schema.get("required", [])) == {"query"}


def test_no_respond_with_revision_tool_remains():
    names = {t.name for t in CHAT_TOOLS}
    assert "respond_with_revision" not in names, \
        "Legacy tool name must not coexist with `respond`"
