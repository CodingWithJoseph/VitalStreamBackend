import hashlib
import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from vitalstream.analytics import baseline_insight
from vitalstream.auth import Authenticator
from vitalstream.config import Settings
from vitalstream.database import Observation, database
from vitalstream.schemas import (
    BatchInput,
    BatchResult,
    Identity,
    Insight,
    ObservationOutput,
    ObservationPage,
    RecordResult,
)


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def output(row: Observation) -> ObservationOutput:
    return ObservationOutput(
        id=row.record_id,
        source=row.source,
        source_record_id=row.source_record_id,
        revision=row.revision,
        metric=row.metric,
        value=row.value,
        unit=row.unit,
        observed_at=utc(row.observed_at),
        synthetic=row.synthetic,
        received_at=utc(row.received_at),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine, sessions = database(settings.database_url)
    auth = Authenticator(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    app = FastAPI(title="VitalStream API", version="0.1.0", lifespan=lifespan)
    app.state.engine, app.state.auth = engine, auth

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Request-ID"] = str(uuid4())
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def ready():
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1 FROM observations LIMIT 1"))
        except SQLAlchemyError:
            raise HTTPException(503, "Database or migrations unavailable") from None
        return {"status": "ready"}

    @app.get("/v1/me", response_model=Identity)
    def me(owner: str = Depends(auth)):
        return Identity(id=owner)

    @app.post("/v1/me/observations:batch", response_model=BatchResult)
    def ingest(batch: BatchInput, owner: str = Depends(auth)):
        results = []
        now = datetime.now(UTC)
        insert = sqlite_insert if engine.dialect.name == "sqlite" else pg_insert
        # The transaction commits before the response. Retries after a lost response are safe.
        with sessions.begin() as session:
            for record in batch.records:
                record_id = str(record.id)
                if (record.synthetic and not settings.allow_synthetic) or record.observed_at > now:
                    results.append(RecordResult(id=record.id, status="rejected"))
                    continue
                payload = record.model_dump(mode="json")
                digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
                values = record.model_dump(exclude={"id"}) | {
                    "owner": owner,
                    "record_id": record_id,
                    "received_at": now,
                    "payload_hash": digest,
                    "deleted": False,
                }
                created = session.execute(
                    insert(Observation)
                    .values(**values)
                    .on_conflict_do_nothing()
                    .returning(Observation.sequence)
                ).scalar_one_or_none()
                row = session.scalar(
                    select(Observation)
                    .where(Observation.owner == owner, Observation.record_id == record_id)
                    .with_for_update()
                )
                if created is not None:
                    status = "created"
                elif row is None:
                    status = "conflict"
                elif row.deleted:
                    status = "deleted"
                elif row.source != record.source or row.source_record_id != record.source_record_id:
                    status = "conflict"
                elif row.revision > record.revision:
                    status = "stale"
                elif row.revision == record.revision:
                    status = "unchanged" if row.payload_hash == digest else "conflict"
                else:
                    for name, value in values.items():
                        setattr(row, name, value)
                    session.flush()
                    status = "updated"
                results.append(RecordResult(id=record.id, status=status))
        return BatchResult(results=results)

    @app.get("/v1/me/observations", response_model=ObservationPage)
    def observations(
        cursor: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=100),
        owner: str = Depends(auth),
    ):
        with sessions() as session:
            rows = list(
                session.scalars(
                    select(Observation)
                    .where(
                        Observation.owner == owner,
                        Observation.deleted.is_(False),
                        Observation.sequence > cursor,
                    )
                    .order_by(Observation.sequence)
                    .limit(limit + 1)
                )
            )
            return ObservationPage(
                items=[output(row) for row in rows[:limit]],
                next_cursor=rows[limit - 1].sequence if len(rows) > limit else None,
            )

    @app.delete("/v1/me/observations/{record_id}", status_code=204)
    def delete_observation(record_id: UUID, owner: str = Depends(auth)):
        with sessions.begin() as session:
            row = session.scalar(
                select(Observation)
                .where(Observation.owner == owner, Observation.record_id == str(record_id))
                .with_for_update()
            )
            if row is None:
                raise HTTPException(404, "Observation not found")
            # A tombstone prevents an old device upload from resurrecting a deleted record.
            row.deleted = True

    @app.get("/v1/me/insights", response_model=Insight)
    def insights(
        source: str = Query("synthetic", min_length=1, max_length=120), owner: str = Depends(auth)
    ):
        now = datetime.now(UTC)
        with sessions() as session:
            rows = list(
                session.execute(
                    select(Observation.observed_at, Observation.value)
                    .where(
                        Observation.owner == owner,
                        Observation.deleted.is_(False),
                        Observation.source == source,
                        Observation.observed_at >= now - timedelta(days=28),
                    )
                    .order_by(Observation.observed_at)
                    .limit(10001)
                )
            )
            if len(rows) > 10000:
                raise HTTPException(422, "Too many readings; daily aggregation is required")
        # Computing from current inputs avoids stale derived records after updates/deletes.
        # JOSEPH-B1: introduce a daily_features table when volume grows. Key it by owner,
        # source, UTC day and feature version; invalidate affected days on upsert/delete.
        # Test that correcting yesterday changes today's insight without double-counting.
        return baseline_insight(rows, source, now)

    return app
