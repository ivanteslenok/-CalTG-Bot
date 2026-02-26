"""Drop meal_type column from meal_log.

Первая миграция: удаляем больше не используемый столбец meal_type.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260226_drop_meal_type"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Удалить столбец meal_type из таблицы meal_log."""
    with op.batch_alter_table("meal_log") as batch_op:
        batch_op.drop_column("meal_type")


def downgrade() -> None:
    """Вернуть столбец meal_type в таблицу meal_log (на случай отката)."""
    with op.batch_alter_table("meal_log") as batch_op:
        batch_op.add_column(sa.Column("meal_type", sa.String(length=20), nullable=True))

