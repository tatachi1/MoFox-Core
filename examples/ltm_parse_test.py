import sys
from pathlib import Path

# Ensure project root on sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from typing import Any

# Import after sys.path injection
from src.memory_graph.long_term_manager import LongTermMemoryManager


class FakeMemoryManager:
    """Minimal stub to satisfy LongTermMemoryManager __init__ signature."""
    def __init__(self) -> None:
        self._initialized = True


def dump_ops(label: str, ops: list[Any]) -> None:
    types = [getattr(op.operation_type, "value", str(op.operation_type)) for op in ops]
    print(f"{label}: count={len(ops)}, types={types}")


def main() -> None:
    ltm = LongTermMemoryManager(memory_manager=FakeMemoryManager())

    # Case 1: Proper JSON array in ```json block
    resp1 = (
        """Here is the plan:\n```json\n[
        {\n  \"operation_type\": \"CREATE_MEMORY\", \n  \"target_id\": \"TEMP_MEM_1\", \n  \"parameters\": {\n    \"subject\": \"我\"\n  }\n}\n]\n```"""
    )
    ops1 = ltm._parse_graph_operations(resp1)
    dump_ops("case1", ops1)

    # Case 2: Generic ``` block (no language tag), single object
    resp2 = (
        """```\n{ \n  \"operation_type\": \"UPDATE_MEMORY\",\n  \"parameters\": {\n    \"memory_id\": \"ABC\", \n    \"updated_fields\": {\n      \"importance\": 0.8\n    }\n  }\n}\n```"""
    )
    ops2 = ltm._parse_graph_operations(resp2)
    dump_ops("case2", ops2)

    # Case 3: Bare JSON embedded in text
    resp3 = 'Some notes: before {"operation_type": "MERGE_MEMORIES", "parameters": {"source_memory_ids": ["A", "B"], "merged_importance": 0.7}} after'
    ops3 = ltm._parse_graph_operations(resp3)
    dump_ops("case3", ops3)

    # Case 4: JSON with comments and trailing comma (needs repair)
    resp4 = (
        """// leading comment\n[
  {\n    \"operation_type\": \"CREATE_NODE\", // inline comment\n    \"parameters\": {\n      \"content\": \"跑步\",\n      \"node_type\": \"主题\",\n      \"memory_id\": \"TEMP_MEM_1\",\n    },\n  },\n]"""
    )
    ops4 = ltm._parse_graph_operations(resp4)
    dump_ops("case4", ops4)

    # Case 5: Completely unstructured text; expect empty list
    resp5 = "The model failed to provide JSON. Please try again."
    ops5 = ltm._parse_graph_operations(resp5)
    dump_ops("case5", ops5)


if __name__ == "__main__":
    main()
