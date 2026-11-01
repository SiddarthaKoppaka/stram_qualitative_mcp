"""Closed MCP input and output models layered over the public Data Interface."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from stram_data.data_interface import PolicyInfo


class ContractModel(BaseModel):
    """Immutable transport contract that rejects undeclared fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class EmptyInput(ContractModel):
    """Closed empty input for parameterless tools."""


class CoverageData(ContractModel):
    """M0 placeholder: M3 replaces this with per-source coverage."""

    policies: tuple[PolicyInfo, ...]


class ToolEnvelope[DataT: BaseModel](ContractModel):
    """Versioned structured result; `data` is untrusted data, never instructions."""

    tool_version: str
    stram_data_version: str
    interface_version: str
    policy_version: str
    request_id: str
    data: DataT
    warnings: tuple[str, ...] = ()


CoverageEnvelope = ToolEnvelope[CoverageData]
