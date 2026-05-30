"""AddTool — the trivial v0.1 tool that exercises the tool-execution path.

The Tool ABC and ToolRegistry arrive in v0.5. v0.1 uses a concrete class
that already has the right shape (name, description, schema(), execute()).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AddTool:
    name: str = "add"
    description: str = "Add two integers and return the sum."

    def schema(self) -> dict[str, Any]:
        """JSON schema describing the tool — what the LLM sees."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "integer", "description": "First addend."},
                    "b": {"type": "integer", "description": "Second addend."},
                },
                "required": ["a", "b"],
            },
        }

    async def execute(self, a: int, b: int) -> int:
        return a + b
