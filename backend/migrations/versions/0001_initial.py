"""Create all durable domain tables with indexed recording foreign keys."""
from alembic import op
import sqlalchemy as sa
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None
NAMES = ["segments", "cards", "entities", "relations", "clusters", "corrections", "queries", "exports", "runs"]

def upgrade() -> None:
    """Install the initial schema; payload content migrations belong in future revisions."""
    op.create_table("sessions", sa.Column("id", sa.String(), primary_key=True), sa.Column("payload", sa.JSON(), nullable=False))
    for name in NAMES:
        op.create_table(name, sa.Column("id", sa.String(), primary_key=True), sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("payload", sa.JSON(), nullable=False))
        op.create_index(f"ix_{name}_session_id", name, ["session_id"])

def downgrade() -> None:
    """Remove initial tables in foreign-key-safe order."""
    for name in reversed(NAMES):
        op.drop_table(name)
    op.drop_table("sessions")
