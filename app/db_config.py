"""Shared PostgreSQL configuration from environment variables."""
import os


DEMO_DATABASE_NAME = "baomatdulieu_demo"
BENCHMARK_DATABASE_NAME = "baomatdulieu_benchmark"
APPLICATION_DATABASE_NAME = "baomatdulieu"


def _required_credentials(user_names, password_names):
    user = next((os.getenv(name) for name in user_names if os.getenv(name)), None)
    password = next((os.getenv(name) for name in password_names if os.getenv(name)), None)
    missing = []
    if not user:
        missing.append(" or ".join(user_names))
    if not password:
        missing.append(" or ".join(password_names))
    if missing:
        raise RuntimeError("Missing required database environment variables: " + ", ".join(missing))
    return user, password


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
        "dbname": os.getenv("POSTGRES_DB", APPLICATION_DATABASE_NAME),
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
    }


def get_demo_db_config():
    """Return the isolated local-demo database configuration.

    The target database name is pinned so a typo or accidental environment
    override cannot redirect the UI or Controlled RAG to the benchmark database.
    """
    database = os.getenv("DEMO_DB_NAME", DEMO_DATABASE_NAME)
    if database != DEMO_DATABASE_NAME:
        raise RuntimeError(
            f"Demo database must be {DEMO_DATABASE_NAME!r}; got {database!r}."
        )
    user, password = _required_credentials(
        ("DEMO_DB_USER", "POSTGRES_USER"),
        ("DEMO_DB_PASSWORD", "POSTGRES_PASSWORD"),
    )
    return {
        "host": os.getenv("DEMO_DB_HOST", os.getenv("POSTGRES_HOST", "localhost")),
        "port": int(os.getenv("DEMO_DB_PORT", os.getenv("POSTGRES_PORT", "5432"))),
        "dbname": DEMO_DATABASE_NAME,
        "user": user,
        "password": password,
    }


def get_benchmark_db_config():
    """Return connection settings for the isolated scale-benchmark database.

    Benchmark-specific host/port/credentials may override POSTGRES_*; otherwise
    the same local server and credentials are reused. The benchmark scripts
    independently enforce their expected database name before doing work.
    """
    user, password = _required_credentials(
        ("BENCHMARK_DB_USER", "POSTGRES_USER"),
        ("BENCHMARK_DB_PASSWORD", "POSTGRES_PASSWORD"),
    )
    database = os.getenv("BENCHMARK_DB_NAME", BENCHMARK_DATABASE_NAME)
    if database != BENCHMARK_DATABASE_NAME:
        raise RuntimeError(
            f"Benchmark database must be {BENCHMARK_DATABASE_NAME!r}; got {database!r}."
        )
    return {
        "host": os.getenv("BENCHMARK_DB_HOST", os.getenv("POSTGRES_HOST", "localhost")),
        "port": int(os.getenv("BENCHMARK_DB_PORT", os.getenv("POSTGRES_PORT", "5432"))),
        "dbname": database,
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
