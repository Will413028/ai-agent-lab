from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from .repository import Busy, NotFound, Repository
from .run_models import Final, Run, RunEvent, RunRequest


class RunStore:
    def __init__(self, repository: Repository):
        self.repository = repository

    async def begin(self, conversation_id: UUID, request: RunRequest, workspace_id: UUID) -> Run:
        # Turn and run allocation share one short transaction; no orphan running turn.
        async with self.repository.connection() as db:
            await self.repository._conversation(db, conversation_id, lock=True)
            turns = await self.repository._turns(db, conversation_id)
            if any(t.status == "running" for t in turns):
                raise Busy
            position = turns[-1].position + 1 if turns else 1
            turn_id = uuid4()
            await db.execute(
                "INSERT INTO agent_lab.turns (id,conversation_id,position,question,status) "
                "VALUES (%s,%s,%s,%s,'running')",
                (turn_id, conversation_id, position, request.goal),
            )
            cursor = await db.execute(
                "INSERT INTO agent_lab.runs "
                "(id,conversation_id,turn_id,workspace_id,goal,status,max_steps,max_calls) "
                "VALUES (%s,%s,%s,%s,%s,'running',%s,%s) RETURNING *",
                (
                    uuid4(),
                    conversation_id,
                    turn_id,
                    workspace_id,
                    request.goal,
                    request.max_steps,
                    request.max_calls,
                ),
            )
            await db.execute(
                "UPDATE agent_lab.conversations SET updated_at=now() WHERE id=%s",
                (conversation_id,),
            )
            return Run.model_validate(await cursor.fetchone())

    async def append(self, event: RunEvent):
        async with self.repository.connection() as db:
            cursor = await db.execute(
                "SELECT * FROM agent_lab.runs WHERE id=%s FOR UPDATE", (event.run_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                raise NotFound
            if row["status"] != "running":
                raise Busy
            cursor = await db.execute(
                "SELECT count(*) AS n FROM agent_lab.run_events WHERE run_id=%s", (event.run_id,)
            )
            if (await cursor.fetchone())["n"] != event.sequence:
                raise Busy
            await db.execute(
                "INSERT INTO agent_lab.run_events VALUES (%s,%s,%s)",
                (event.run_id, event.sequence, Jsonb(event.model_dump(mode="json"))),
            )
            if isinstance(event.data, Final):
                final = event.data
                await db.execute(
                    "UPDATE agent_lab.runs SET status=%s,answer=%s,error_code=%s,finished_at=now() "
                    "WHERE id=%s",
                    (final.status, final.answer, final.code, event.run_id),
                )
                status = {"succeeded": "completed", "limit": "failed"}.get(
                    final.status, final.status
                )
                await db.execute(
                    "UPDATE agent_lab.turns SET status=%s,answer=%s,error_code=%s,"
                    "finished_at=now() "
                    "WHERE id=%s AND status='running'",
                    (status, final.answer, final.code, row["turn_id"]),
                )
                await db.execute(
                    "UPDATE agent_lab.conversations SET updated_at=now() WHERE id=%s",
                    (row["conversation_id"],),
                )

    async def list(self, conversation_id: UUID) -> list[Run]:
        async with self.repository.connection() as db:
            await self.repository._conversation(db, conversation_id)
            cursor = await db.execute(
                "SELECT * FROM agent_lab.runs WHERE conversation_id=%s ORDER BY created_at,id",
                (conversation_id,),
            )
            return [Run.model_validate(row) for row in await cursor.fetchall()]

    async def get(self, conversation_id: UUID, run_id: UUID) -> Run:
        async with self.repository.connection() as db:
            cursor = await db.execute(
                "SELECT * FROM agent_lab.runs WHERE id=%s AND conversation_id=%s FOR SHARE",
                (run_id, conversation_id),
            )
            row = await cursor.fetchone()
            if row is None:
                raise NotFound
            cursor = await db.execute(
                "SELECT payload FROM agent_lab.run_events WHERE run_id=%s ORDER BY sequence",
                (run_id,),
            )
            return Run(
                **row,
                events=[RunEvent.model_validate(r["payload"]) for r in await cursor.fetchall()],
            )

    async def recover(self):
        async with self.repository.connection() as db:
            await db.execute(
                "UPDATE agent_lab.runs SET status='cancelled',error_code='interrupted',"
                "finished_at=now() WHERE status='running'"
            )
