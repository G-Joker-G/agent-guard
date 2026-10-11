"""pytest 配置：独立测试库 + 每个测试前重置数据。"""

import os
import sys
from pathlib import Path

# 必须在导入 app.db 之前设置，保证测试用独立 SQLite 库
_TEST_DB = "/tmp/agent_guard_test.db"
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)
os.environ["AGENT_GUARD_DB_PATH"] = _TEST_DB

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402

db.init_db()
client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_between_tests():
    """每个测试前清空业务数据并重建种子（急停解除）。"""
    client.post("/api/admin/reset")
    yield


@pytest.fixture()
def api():
    return client
