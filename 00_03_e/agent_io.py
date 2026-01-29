# lesson3-create-an-agent-inventory/inventory_io.py
import os
import json
from agent_models import AgentInventory

def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def inventory_exists(path: str) -> bool:
    return os.path.exists(path)

def load_inventory(path: str) -> AgentInventory:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return AgentInventory(**data)

def save_inventory(path: str, inventory: AgentInventory) -> None:
    ensure_dir(os.path.dirname(path) or ".")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(inventory.model_dump(), f, indent=2)
