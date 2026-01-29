# lesson4-add-runtime-guardrails/guardrails.py
import os
import re
from typing import Optional, Tuple

from agents import (
    Agent,
    Runner,
    GuardrailFunctionOutput,
)
from pydantic import BaseModel

from agent_models import AgentInventory, AgentInventoryItem
from observability import log_event

# ---------------------------------------------------------------------------
# Guardrail output schema (what we log)
# ---------------------------------------------------------------------------
class GuardrailDecision(BaseModel):
    is_allowed: bool
    reason: str
    matched_rule: str

# ---------------------------------------------------------------------------
# Optional LLM-based guardrail (kept simple + explainable)
# We use it to catch "obviously bad" user intent that string checks miss.
# ---------------------------------------------------------------------------
class IntentCheck(BaseModel):
    is_safe: bool
    reason: str

intent_guardrail_agent = Agent(
    name="Intent Guardrail",
    model="gpt-5.2",
    instructions=(
        "You are a strict safety gate for an enterprise shopping assistant. "
        "Flag as unsafe if the request includes any of these themes:\n"
        "- writing to system directories like /etc, /usr, or ~/.ssh\n"
        "- exfiltrating secrets, API keys, or credentials\n"
        "- modifying financial ledgers, payroll, invoices, or accounting records\n"
        "- changing production configs or production files\n\n"
        "If unsafe, set is_safe=false and explain why briefly. Otherwise set is_safe=true."
    ),
    output_type=IntentCheck,
)

# ---------------------------------------------------------------------------
# Helper: pull target read/write paths out of the prompt
# (We keep prompt format consistent so this stays reliable.)
# ---------------------------------------------------------------------------
def extract_paths_from_prompt(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    read_match = re.search(r"Read the shopping notes at:\s*(.+?)\.\s", prompt)
    write_match = re.search(r"write a JSON summary to:\s*(.+?)\.\s", prompt)
    read_path = read_match.group(1).strip() if read_match else None
    write_path = write_match.group(1).strip() if write_match else None
    return read_path, write_path

def is_subpath(path: str, parent_dir: str) -> bool:
    # Normalize and compare to prevent "../../" tricks
    p = os.path.abspath(path)
    parent = os.path.abspath(parent_dir)
    return os.path.commonpath([p, parent]) == parent

# ---------------------------------------------------------------------------
# The runtime guardrail function
# - Checks inventory allowlists for read/write
# - Enforces "writes must stay in OUT_DIR"
# - Uses LLM intent check as a second line of defense
# ---------------------------------------------------------------------------
async def runtime_guardrail(ctx, agent, input_data: str) -> GuardrailFunctionOutput:
    """
    Input guardrail for the shopping agent.
    """
    # These are provided by main.py via ctx.context
    inventory: AgentInventory = ctx.context["inventory"]
    log_path: str = ctx.context["event_log_path"]
    out_dir: str = ctx.context["out_dir"]

    read_path, write_path = extract_paths_from_prompt(input_data)

    # Find this agent’s inventory row
    inv_item: Optional[AgentInventoryItem] = None
    for a in inventory.agents:
        if a.name == agent.name:
            inv_item = a
            break

    if inv_item is None:
        decision = GuardrailDecision(
            is_allowed=False,
            reason="Agent is not present in the inventory, so it cannot run.",
            matched_rule="inventory.required",
        )
        log_event(log_path, "guardrail_blocked", agent_name=agent.name, decision=decision.model_dump())
        return GuardrailFunctionOutput(output_info=decision, tripwire_triggered=True)

    # Rule 1: inventory allowlisted read
    if read_path and read_path not in inv_item.data_access.reads:
        decision = GuardrailDecision(
            is_allowed=False,
            reason=f"Read path is not allowlisted in inventory: {read_path}",
            matched_rule="data_access.read_allowlist",
        )
        log_event(log_path, "guardrail_blocked", agent_name=agent.name, decision=decision.model_dump())
        return GuardrailFunctionOutput(output_info=decision, tripwire_triggered=True)

    # Rule 2: inventory allowlisted write
    if write_path and write_path not in inv_item.data_access.writes:
        decision = GuardrailDecision(
            is_allowed=False,
            reason=f"Write path is not allowlisted in inventory: {write_path}",
            matched_rule="data_access.write_allowlist",
        )
        log_event(log_path, "guardrail_blocked", agent_name=agent.name, decision=decision.model_dump())
        return GuardrailFunctionOutput(output_info=decision, tripwire_triggered=True)

    # Rule 3: writes must stay in OUT_DIR (defense in depth)
    if write_path and not is_subpath(write_path, out_dir):
        decision = GuardrailDecision(
            is_allowed=False,
            reason=f"Write path must stay inside out directory: {out_dir}",
            matched_rule="writes.restrict_to_out_dir",
        )
        log_event(log_path, "guardrail_blocked", agent_name=agent.name, decision=decision.model_dump())
        return GuardrailFunctionOutput(output_info=decision, tripwire_triggered=True)

    # Rule 4: LLM intent safety check (second line of defense)
    intent_result = await Runner.run(intent_guardrail_agent, input_data, context=ctx.context)
    intent = intent_result.final_output_as(IntentCheck)

    if not intent.is_safe:
        decision = GuardrailDecision(
            is_allowed=False,
            reason=intent.reason,
            matched_rule="intent.safety_check",
        )
        log_event(log_path, "guardrail_blocked", agent_name=agent.name, decision=decision.model_dump())
        return GuardrailFunctionOutput(output_info=decision, tripwire_triggered=True)

    decision = GuardrailDecision(
        is_allowed=True,
        reason="Guardrail checks passed. Proceeding.",
        matched_rule="allow",
    )
    log_event(log_path, "guardrail_allowed", agent_name=agent.name, decision=decision.model_dump())
    return GuardrailFunctionOutput(output_info=decision, tripwire_triggered=False)