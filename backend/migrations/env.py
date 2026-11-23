from alembic import context
from app.core.database import Base, engine
from app.common import models
from app.modules.time_tracking import models as time_models
from app.modules.risk_management import models as risk_models


def run_migrations_online():
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=Base.metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_offline():
    context.configure(
        url=str(engine.url), target_metadata=Base.metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
