"""Alembic migration environment bound to configured local data directory."""
from alembic import context
from app.models.database import engine, metadata
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
