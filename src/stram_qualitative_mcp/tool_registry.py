"""Reviewed V1 tool definitions and their reproducible schema hashes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pydantic import BaseModel

from stram_qualitative_mcp.tool_models import CoverageEnvelope, EmptyInput


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One direct, read-only Data Interface operation."""

    name: str
    description: str
    scope: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    timeout_seconds: float

    def definition(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "scope": self.scope,
            "inputSchema": self.input_model.model_json_schema(),
            "outputSchema": self.output_model.model_json_schema(),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }

    def schema_hash(self) -> str:
        encoded = json.dumps(self.definition(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


TOOL_SPECS = (
    ToolSpec(
        "qual_describe_coverage",
        "Describe the availability policies in force. A placeholder until coverage is built.",
        "qual:discover",
        EmptyInput,
        CoverageEnvelope,
        10.0,
    ),
)

TOOLS_BY_NAME = {spec.name: spec for spec in TOOL_SPECS}


def exported_definitions() -> dict[str, object]:
    """Return stable definitions and hashes for review and drift detection."""

    return {
        "tools": [{**spec.definition(), "schemaHash": spec.schema_hash()} for spec in TOOL_SPECS]
    }
