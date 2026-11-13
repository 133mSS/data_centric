import os
import sys
from pathlib import Path
from unittest.mock import patch

APP_DIR = str(Path(__file__).resolve().parents[1] / "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import db_config


def test_demo_database_config_uses_dedicated_database_and_shared_credentials():
    with patch.dict(os.environ, {
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5433",
        "POSTGRES_USER": "lab_user",
        "POSTGRES_PASSWORD": "not-a-real-secret",
    }, clear=True):
        config = db_config.get_demo_db_config()

    assert config == {
        "host": "localhost",
        "port": 5433,
        "dbname": "baomatdulieu_demo",
        "user": "lab_user",
        "password": "not-a-real-secret",
    }


def test_demo_database_config_rejects_benchmark_database_override():
    with patch.dict(os.environ, {
        "POSTGRES_USER": "lab_user",
        "POSTGRES_PASSWORD": "not-a-real-secret",
        "DEMO_DB_NAME": "baomatdulieu_benchmark",
    }, clear=True):
        try:
            db_config.get_demo_db_config()
        except RuntimeError as exc:
            assert "baomatdulieu_demo" in str(exc)
        else:
            raise AssertionError("Demo config must reject a benchmark database override.")


def test_demo_database_config_supports_explicit_connection_overrides():
    with patch.dict(os.environ, {
        "POSTGRES_USER": "base_user",
        "POSTGRES_PASSWORD": "base_password",
        "DEMO_DB_HOST": "demo-db",
        "DEMO_DB_PORT": "5544",
        "DEMO_DB_USER": "demo_user",
        "DEMO_DB_PASSWORD": "demo_password",
        "DEMO_DB_NAME": "baomatdulieu_demo",
    }, clear=True):
        config = db_config.get_demo_db_config()

    assert config["host"] == "demo-db"
    assert config["port"] == 5544
    assert config["dbname"] == "baomatdulieu_demo"
    assert config["user"] == "demo_user"
    assert config["password"] == "demo_password"
