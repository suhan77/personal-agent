from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

CHECKPOINT_ALLOWED_MSGPACK_MODULES = [
    ("langmem.short_term.summarization", "RunningSummary"),
]


@asynccontextmanager
async def open_checkpointer(
    checkpoint_db_path: Path,
) -> AsyncIterator[AsyncSqliteSaver]:
    """에이전트 실행 중 사용할 SQLite 체크포인터를 연다."""
    checkpoint_db_path.parent.mkdir(parents=True, exist_ok=True)
    serializer = JsonPlusSerializer(
        allowed_msgpack_modules=CHECKPOINT_ALLOWED_MSGPACK_MODULES
    )

    async with aiosqlite.connect(str(checkpoint_db_path)) as connection:
        checkpointer = AsyncSqliteSaver(connection, serde=serializer)
        await checkpointer.setup()
        yield checkpointer


async def delete_conversation(checkpointer: AsyncSqliteSaver, conversation_id: str) -> None:
    """Remove all LangGraph checkpoints and writes for one conversation."""
    if not isinstance(conversation_id, str) or not conversation_id.strip():
        raise ValueError("Conversation id is required")

    await checkpointer.conn.execute(
        "DELETE FROM checkpoints WHERE thread_id = ?",
        (conversation_id,),
    )
    await checkpointer.conn.execute(
        "DELETE FROM writes WHERE thread_id = ?",
        (conversation_id,),
    )
    await checkpointer.conn.commit()
