from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

#shared vocabulary for risk that both humans and systems can understand
class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"

#defines what data an agent can touch, separated into read and write access
class DataAccess(BaseModel):
    reads: List[str] = Field(default_factory=list)
    writes: List[str] = Field(default_factory=list)

#records what capabilities an agent has access too
class ToolAccess(BaseModel):
    name: str
    type: str  # "function_tool" | "web_search" | "agent_tool"
    notes: Optional[str] = None

#core governance unit: one row per agent
class AgentInventoryItem(BaseModel):
    agent_id: str
    name: str
    purpose: str
    owner: str
    environments: List[str]
    risk_level: RiskLevel

    tool_access: List[ToolAccess] = Field(default_factory=list)
    data_access: DataAccess = Field(default_factory=DataAccess)

    requires_human_review: bool = False
    review_triggers: List[str] = Field(default_factory=list)

#system of record for all agents
class AgentInventory(BaseModel):
    version: str = "1.0"
    description: str
    agents: List[AgentInventoryItem]

#structured application output
class AgentSummaryOutput(BaseModel):
    input_file: str
    budget: Optional[str]
    key_needs: List[str]
    summary: str
    output_file: str
    created_at: str