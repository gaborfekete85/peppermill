"""
Tests for the add tool.
"""
import pytest

from peppermill.agent.tools.add import AddTool


async def test_add_tool_is_a_tool():
    tool = AddTool()
    res = await tool.execute(a=2, b=3)
    assert res == 5

@pytest.mark.parametrize(
    "a,b,expected",
    [(0, 0, 0), (-7, 10, 3), (100, -50, 50), (1, 1, 2)],
)
async def test_add_handles_various_int_pairs(a, b, expected):
    tool = AddTool()
    assert await tool.execute(a=a, b=b) == expected

def test_add_schema_declares_name_description_and_required_params():
    tool = AddTool()
    schema = tool.schema()
    assert schema["name"] == "add"
    assert "description" in schema and schema["description"]
    props = schema["parameters"]["properties"]
    assert "a" in props and props["a"]["type"] == "integer"
    assert "b" in props and props["b"]["type"] == "integer"
    assert set(schema["parameters"]["required"]) == {"a", "b"}
