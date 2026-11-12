
"""Shared PostgreSQL configuration from environment variables."""
import os


def get_db_config():
    required = ("POSTGRES_USER", "POSTGRES_PASSWORD")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(
            "Missing required database environment variables: "
            + ", ".join(missing)
        )

    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "baomatdulieu"),
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
    }


def get_benchmark_db_config():
    """Return connection settings for the isolated scale-benchmark database.

    Benchmark-specific host/port/credentials may override POSTGRES_*; otherwise
    the same local server and credentials are reused. The benchmark scripts
    independently enforce their expected database name before doing work.
    """
    user = os.getenv("BENCHMARK_DB_USER") or os.getenv("POSTGRES_USER")
    password = os.getenv("BENCHMARK_DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD")
    missing = []
    if not user:
        missing.append("POSTGRES_USER (or BENCHMARK_DB_USER)")
    if not password:
        missing.append("POSTGRES_PASSWORD (or BENCHMARK_DB_PASSWORD)")
    if missing:
        raise RuntimeError("Missing required database environment variables: " + ", ".join(missing))

    return {
        "host": os.getenv("BENCHMARK_DB_HOST", os.getenv("POSTGRES_HOST", "localhost")),
        "port": int(os.getenv("BENCHMARK_DB_PORT", os.getenv("POSTGRES_PORT", "5432"))),
        "dbname": os.getenv("BENCHMARK_DB_NAME", "baomatdulieu_benchmark"),
        "user": user,
        "password": password,
    }


def require_database(conn, expected_db, operation="database operation"):
    """Fail closed when a script is connected to an unexpected database."""
    with conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        row = cur.fetchone()
    actual_db = row[0] if row else None
    if actual_db != expected_db:
        raise RuntimeError(
            f"Safety stop for {operation}: connected to {actual_db!r}, "
            f"expected {expected_db!r}. No operation should continue."
        )
    return actual_db
