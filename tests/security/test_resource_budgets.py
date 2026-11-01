from __future__ import annotations

import pytest
from pydantic import ValidationError

from stram_qualitative_mcp.tool_models import EmptyInput


def test_tool_inputs_reject_undeclared_fields() -> None:
    with pytest.raises(ValidationError):
        EmptyInput.model_validate({"limit": 1})
