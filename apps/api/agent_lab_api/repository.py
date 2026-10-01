from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .conversation_models import Conversation, ConversationDetail, LoveReport, SavedReport, Turn
from .database import connection_info


class NotFound(Exception):
    pass


class Busy(Exception):
    pass


class StaleReport(Exception):
    pass


class Repository:
    @asynccontextmanager
    async def connection(self, *, autocommit: bool = False):
        async with await AsyncConnection.connect(
            connection_info(),
            row_factory=dict_row,
            autocommit=autocommit,
            options="-c statement_timeout=3000 -c lock_timeout=1500",
        ) as db:
            yield db

    async def _conversation(self, db, conversation_id: UUID, *, lock: bool = False):
        cursor = await db.execute(
            "SELECT * FROM agent_lab.conversations WHERE id=%s" + (" FOR UPDATE" if lock else ""),
            (conversation_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            raise NotFound
        return row

    async def _turns(self, db, conversation_id: UUID) -> list[Turn]:
        cursor = await db.execute(
            "SELECT * FROM agent_lab.turns WHERE conversation_id=%s ORDER BY position",
            (conversation_id,),
        )
        return [Turn.model_validate(row) for row in await cursor.fetchall()]

    async def create(self, title: str) -> Conversation:
        async with self.connection() as db:
            cursor = await db.execute(
                "INSERT INTO agent_lab.conversations (id,title) VALUES (%s,%s) RETURNING *",
                (uuid4(), title),
            )
            return Conversation.model_validate(await cursor.fetchone())

    async def list(self) -> list[Conversation]:
        async with self.connection() as db:
            cursor = await db.execute(
                "SELECT * FROM agent_lab.conversations ORDER BY updated_at DESC,id"
            )
            return [Conversation.model_validate(row) for row in await cursor.fetchall()]

    async def detail(self, conversation_id: UUID) -> ConversationDetail:
        async with self.connection() as db:
            # Serialize against deletion and turn writes for one coherent detail snapshot.
            row = await self._conversation(db, conversation_id, lock=True)
            return ConversationDetail(**row, turns=await self._turns(db, conversation_id))

    async def delete(self, conversation_id: UUID) -> None:
        async with self.connection() as db:
            await self._conversation(db, conversation_id, lock=True)
            turns = await self._turns(db, conversation_id)
            if any(turn.status == "running" for turn in turns):
                raise Busy
            await db.execute("DELETE FROM agent_lab.conversations WHERE id=%s", (conversation_id,))

    async def begin(self, conversation_id: UUID, question: str) -> tuple[Turn, list[Turn]]:
        async with self.connection() as db:
            await self._conversation(db, conversation_id, lock=True)
            turns = await self._turns(db, conversation_id)
            if any(turn.status == "running" for turn in turns):
                raise Busy
            position = turns[-1].position + 1 if turns else 1
            cursor = await db.execute(
                "INSERT INTO agent_lab.turns "
                "(id,conversation_id,position,question,status) VALUES (%s,%s,%s,%s,'running') "
                "RETURNING *",
                (uuid4(), conversation_id, position, question),
            )
            await db.execute(
                "UPDATE agent_lab.conversations SET updated_at=now() WHERE id=%s",
                (conversation_id,),
            )
            return Turn.model_validate(await cursor.fetchone()), turns

    async def finish(self, turn: Turn, answer: str, status: str, code: str | None = None) -> None:
        async with self.connection() as db:
            await self._conversation(db, turn.conversation_id, lock=True)
            cursor = await db.execute(
                "UPDATE agent_lab.turns SET answer=%s,status=%s,error_code=%s,"
                "finished_at=now() WHERE id=%s AND conversation_id=%s AND status='running' "
                "RETURNING id",
                (answer, status, code, turn.id, turn.conversation_id),
            )
            if await cursor.fetchone() is None:
                raise Busy
            await db.execute(
                "UPDATE agent_lab.conversations SET updated_at=now() WHERE id=%s",
                (turn.conversation_id,),
            )

    async def report_source(self, conversation_id: UUID) -> tuple[int, list[Turn]]:
        detail = await self.detail(conversation_id)
        if not detail.turns or not any(t.status == "completed" for t in detail.turns):
            raise StaleReport
        if any(t.status == "running" for t in detail.turns):
            raise Busy
        return detail.turns[-1].position, detail.turns

    async def save_report(
        self, conversation_id: UUID, position: int, report: LoveReport
    ) -> SavedReport:
        async with self.connection() as db:
            await self._conversation(db, conversation_id, lock=True)
            turns = await self._turns(db, conversation_id)
            if not turns or turns[-1].position != position or turns[-1].status == "running":
                raise StaleReport
            cursor = await db.execute(
                "INSERT INTO agent_lab.reports "
                "(id,conversation_id,source_position,content) VALUES (%s,%s,%s,%s) RETURNING *",
                (uuid4(), conversation_id, position, Jsonb(report.model_dump())),
            )
            return SavedReport.model_validate(await cursor.fetchone())

    async def reports(self, conversation_id: UUID) -> list[SavedReport]:
        async with self.connection() as db:
            await self._conversation(db, conversation_id, lock=True)
            cursor = await db.execute(
                "SELECT * FROM agent_lab.reports WHERE conversation_id=%s "
                "ORDER BY created_at DESC,id",
                (conversation_id,),
            )
            return [SavedReport.model_validate(row) for row in await cursor.fetchall()]

    async def recover_interrupted(self) -> None:
        async with self.connection() as db:
            await db.execute(
                "UPDATE agent_lab.turns SET status='cancelled',error_code='interrupted',"
                "finished_at=now() WHERE status='running'"
            )
