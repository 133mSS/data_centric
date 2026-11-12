import os
import unittest
from unittest.mock import patch

from app.db_config import get_benchmark_db_config, get_db_config, require_database


class FakeCursor:
    def __init__(self, database):
        self.database = database
        self.query = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query):
        self.query = query

    def fetchone(self):
        return (self.database,)


class FakeConnection:
    def __init__(self, database):
        self.database = database

    def cursor(self):
        return FakeCursor(self.database)


class DatabaseBoundaryTests(unittest.TestCase):
    def test_application_database_uses_postgres_db(self):
        env = {
            "POSTGRES_USER": "test-user",
            "POSTGRES_PASSWORD": "not-a-real-password",
            "POSTGRES_DB": "baomatdulieu",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(get_db_config()["dbname"], "baomatdulieu")

    def test_benchmark_database_does_not_follow_postgres_db(self):
        env = {
            "POSTGRES_USER": "test-user",
            "POSTGRES_PASSWORD": "not-a-real-password",
            "POSTGRES_DB": "baomatdulieu",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                get_benchmark_db_config()["dbname"], "baomatdulieu_benchmark"
            )

    def test_benchmark_database_can_be_explicitly_overridden(self):
        env = {
            "POSTGRES_USER": "test-user",
            "POSTGRES_PASSWORD": "not-a-real-password",
            "POSTGRES_DB": "baomatdulieu",
            "BENCHMARK_DB_NAME": "custom_benchmark",
        }
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(get_benchmark_db_config()["dbname"], "custom_benchmark")


    def test_benchmark_connection_overrides_are_used_without_changing_app_config(self):
        env = {
            "POSTGRES_USER": "app-user",
            "POSTGRES_PASSWORD": "app-password",
            "POSTGRES_HOST": "app-host",
            "POSTGRES_PORT": "5432",
            "POSTGRES_DB": "baomatdulieu",
            "BENCHMARK_DB_USER": "bench-user",
            "BENCHMARK_DB_PASSWORD": "bench-password",
            "BENCHMARK_DB_HOST": "bench-host",
            "BENCHMARK_DB_PORT": "5544",
        }
        with patch.dict(os.environ, env, clear=True):
            benchmark = get_benchmark_db_config()
            app = get_db_config()
        self.assertEqual(benchmark["user"], "bench-user")
        self.assertEqual(benchmark["password"], "bench-password")
        self.assertEqual(benchmark["host"], "bench-host")
        self.assertEqual(benchmark["port"], 5544)
        self.assertEqual(app["user"], "app-user")
        self.assertEqual(app["host"], "app-host")

    def test_require_database_accepts_expected_database(self):
        self.assertEqual(
            require_database(FakeConnection("baomatdulieu"), "baomatdulieu"),
            "baomatdulieu",
        )

    def test_require_database_rejects_wrong_database(self):
        with self.assertRaisesRegex(RuntimeError, "expected 'baomatdulieu'"):
            require_database(FakeConnection("baomatdulieu_benchmark"), "baomatdulieu")


if __name__ == "__main__":
    unittest.main()
