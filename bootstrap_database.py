"""Bring fresh, legacy, and Alembic-managed databases to the current schema.

스키마의 유일한 소유자는 Alembic이다. 이 스크립트는 DDL을 직접 실행하지 않고,
현재 DB 상태를 보고 올바른 Alembic 명령만 고른다.

- 이미 Alembic이 관리하는 DB  → upgrade head
- 빈 DB                       → upgrade head (초기 리비전이 전부 생성한다)
- create_all 시절의 레거시 DB → 실제 스키마에 맞는 리비전으로 stamp 후 upgrade head
"""

import asyncio
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, inspect

from app.core.database import engine

# create_all이 만든 레거시 DB는 이미 일부 리비전만큼의 스키마를 갖고 있다.
# 어디까지 반영돼 있는지는 chat_sessions 컬럼으로 판별한다.
INITIAL_REVISION = "20260722_init"
STT_REVISION = "20260722_stt"
STAGE_REVISION = "20260722_stage"


class SchemaState:
    """Alembic 명령을 고르는 데 필요한 최소한의 DB 상태."""

    def __init__(self, versioned: bool, tables: set[str], chat_session_columns: set[str]) -> None:
        self.versioned = versioned
        self.tables = tables
        self.chat_session_columns = chat_session_columns

    @property
    def is_legacy(self) -> bool:
        """Alembic 이력은 없는데 테이블은 있는, create_all 시절의 DB."""
        return not self.versioned and bool(self.tables)

    @property
    def legacy_stamp_target(self) -> str:
        """레거시 DB가 실제로 도달해 있는 리비전."""
        if "stage" in self.chat_session_columns:
            return STAGE_REVISION
        if "stt_session_id" in self.chat_session_columns:
            return STT_REVISION
        return INITIAL_REVISION


def read_state(sync_connection: Connection) -> SchemaState:
    inspector = inspect(sync_connection)
    tables = set(inspector.get_table_names())
    columns: set[Any] = (
        {column["name"] for column in inspector.get_columns("chat_sessions")}
        if "chat_sessions" in tables
        else set()
    )
    return SchemaState(
        versioned="alembic_version" in tables,
        tables=tables - {"alembic_version"},
        chat_session_columns=columns,
    )


async def read_schema_state() -> SchemaState:
    async with engine.connect() as connection:
        state = await connection.run_sync(read_state)
    await engine.dispose()
    return state


def main() -> None:
    state = asyncio.run(read_schema_state())
    config = Config("alembic.ini")

    if state.is_legacy:
        target = state.legacy_stamp_target
        print(f"[bootstrap] Alembic 이력이 없는 레거시 DB — {target} 리비전으로 stamp 합니다")
        command.stamp(config, target)

    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
