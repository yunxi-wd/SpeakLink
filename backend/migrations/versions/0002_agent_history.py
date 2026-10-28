"""Persist agent executions and their role messages without changing existing data."""
from alembic import op
import sqlalchemy as sa
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Create durable execution history and session indexes."""
    for name in ["agent_runs", "agent_events"]:
        op.create_table(name, sa.Column("id", sa.String(), primary_key=True), sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False), sa.Column("payload", sa.JSON(), nullable=False))
        op.create_index(f"ix_{name}_session_id", name, ["session_id"])

def downgrade() -> None:
    """Remove execution history only; domain recordings remain intact."""
    op.drop_table("agent_events")
    op.drop_table("agent_runs")
