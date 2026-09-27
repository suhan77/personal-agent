"""Checkpointed approval gate for filesystem writes."""
import difflib
import hashlib
import os
import tempfile

from langchain_core.messages import ToolMessage
from langgraph.types import interrupt

from personal_agent.tools.filesystem import MAX_TEXT_BYTES, resolve_workspace_file


def prepare_file_change(state):
    calls = state["messages"][-1].tool_calls
    if len(calls) != 1:
        raise ValueError("File changes must be proposed one at a time")
    call = calls[0]
    args = call["args"]
    path = args["path"]
    target = resolve_workspace_file(state["working_directory"], path)
    creation = call["name"] == "create_file"
    if creation:
        if target.exists():
            raise FileExistsError(target)
        if not target.parent.is_dir():
            raise FileNotFoundError(target.parent)
        before = ""
        after = args.get("content", "")
        fingerprint = None
    else:
        if not target.is_file() or target.stat().st_size > MAX_TEXT_BYTES:
            raise ValueError("File is missing or too large")
        raw = target.read_bytes()
        before = raw.decode("utf-8")
        old_text, new_text = args["old_text"], args["new_text"]
        if not old_text or before.count(old_text) != 1:
            raise ValueError("Original text must appear exactly once")
        after = before.replace(old_text, new_text, 1)
        fingerprint = hashlib.sha256(raw).hexdigest()
    if before == after or len(after.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError("Change is empty or too large")
    diff = "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile=path, tofile=path))
    return {"file_change": {"path": path, "diff": diff, "operation": call["name"], "after": after, "fingerprint": fingerprint, "call_id": call["id"]}}


def review_file_change(state):
    proposal = state["file_change"]
    decision = interrupt({"kind": "file_edit_proposal", "path": proposal["path"], "diff": proposal["diff"], "operation": proposal["operation"]})
    return {"file_decision": decision}


def apply_file_change(state):
    proposal = state["file_change"]
    path = proposal["path"]
    after = proposal["after"]
    fingerprint = proposal["fingerprint"]
    creation = proposal["operation"] == "create_file"
    decision = state["file_decision"]
    if decision != "approve":
        result = "사용자가 파일 변경을 거부했습니다. 파일은 수정되지 않았습니다."
    else:
        # Re-resolve and compare immediately before writing; never overwrite external edits.
        current = resolve_workspace_file(state["working_directory"], path)
        if creation:
            with current.open("x", encoding="utf-8") as handle:
                handle.write(after)
        else:
            if hashlib.sha256(current.read_bytes()).hexdigest() != fingerprint:
                raise ValueError("File changed after review; request a new proposal")
            descriptor, temporary = tempfile.mkstemp(dir=current.parent, prefix=".personal-agent-")
            try:
                os.fchmod(descriptor, current.stat().st_mode)
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(after)
                os.replace(temporary, current)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        result = f"사용자가 승인한 변경을 {path}에 적용했습니다."
    return {"messages": [ToolMessage(content=result, tool_call_id=proposal["call_id"])]}
