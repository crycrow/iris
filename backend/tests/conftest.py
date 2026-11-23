

import os
from pathlib import Path
import sys



os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SECRET_KEY"] = "isolated-tests-only-not-a-production-secret"
os.environ["SEED_DEMO"] = "false"
os.environ["SCHEDULER_ENABLED"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
