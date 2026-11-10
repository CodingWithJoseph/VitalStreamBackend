"""Initial observations and ownership boundary."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    op.create_table(
        "observations",
        sa.Column("sequence", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner", sa.String(64), nullable=False),
        sa.Column("record_id", sa.String(36), nullable=False),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("source_record_id", sa.String(200), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("metric", sa.String(40), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(16), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("synthetic", sa.Boolean(), nullable=False),
        sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("owner", "record_id", name="uq_owner_record"),
        sa.UniqueConstraint("owner", "source", "source_record_id", name="uq_owner_source_record"),
    )
    op.create_index("ix_observations_owner", "observations", ["owner"])
    op.create_index("ix_observations_observed_at", "observations", ["observed_at"])


def downgrade():
    op.drop_table("observations")
