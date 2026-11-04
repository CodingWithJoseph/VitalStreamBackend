from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("owner", "record_id", name="uq_owner_record"),
        UniqueConstraint("owner", "source", "source_record_id", name="uq_owner_source_record"),
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    record_id: Mapped[str] = mapped_column(String(36))
    source: Mapped[str] = mapped_column(String(120))
    source_record_id: Mapped[str] = mapped_column(String(200))
    revision: Mapped[int] = mapped_column(BigInteger)
    metric: Mapped[str] = mapped_column(String(40))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(16))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    synthetic: Mapped[bool]
    deleted: Mapped[bool] = mapped_column(default=False)
    payload_hash: Mapped[str] = mapped_column(String(64))


def database(url: str):
    options = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=options, pool_pre_ping=True)
    return engine, sessionmaker(engine, expire_on_commit=False)
