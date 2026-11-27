from collections.abc import Sequence

from alembic import op
from procrastinate.schema import SchemaManager

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DROP_PROCRASTINATE_OBJECTS = """
DO $$
DECLARE
    object_name text;
BEGIN
    FOR object_name IN
        SELECT oid::regprocedure::text FROM pg_proc
        WHERE proname LIKE 'procrastinate\\_%%' AND pronamespace = current_schema()::regnamespace
    LOOP
        EXECUTE 'DROP FUNCTION ' || object_name || ' CASCADE';
    END LOOP;
    DROP TABLE IF EXISTS procrastinate_events, procrastinate_periodic_defers,
        procrastinate_jobs, procrastinate_workers CASCADE;
    DROP TYPE IF EXISTS procrastinate_job_to_defer_v2, procrastinate_job_event_type,
        procrastinate_job_status, procrastinate_lock_mode CASCADE;
END $$
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(SchemaManager.get_schema().replace("%", "%%"))


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DROP_PROCRASTINATE_OBJECTS)
