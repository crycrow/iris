from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("risk_types", sa.Column("object_kind", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("risk_types", "object_kind")
