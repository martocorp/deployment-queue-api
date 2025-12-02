"""Snowflake database connection handling."""

from contextlib import contextmanager
from typing import Any, Generator

import snowflake.connector
from snowflake.connector import DictCursor
from snowflake.connector.connection import SnowflakeConnection

from .config import get_settings


def _get_connection_params() -> dict[str, Any]:
    """Build Snowflake connection parameters supporting password or key-pair auth."""
    settings = get_settings()
    params: dict[str, Any] = {
        "account": settings.snowflake_account,
        "user": settings.snowflake_user,
        "warehouse": settings.snowflake_warehouse,
        "database": settings.snowflake_database,
        "schema": settings.snowflake_schema,
    }

    if settings.snowflake_private_key_path:
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization

        with open(settings.snowflake_private_key_path, "rb") as key_file:
            passphrase = None
            if settings.snowflake_private_key_passphrase:
                passphrase = settings.snowflake_private_key_passphrase.encode()

            p_key = serialization.load_pem_private_key(
                key_file.read(),
                password=passphrase,
                backend=default_backend(),
            )
        params["private_key"] = p_key
    else:
        params["password"] = settings.snowflake_password

    return params


@contextmanager
def get_connection() -> Generator[SnowflakeConnection, None, None]:
    """Context manager for Snowflake connections."""
    conn = snowflake.connector.connect(**_get_connection_params())
    try:
        yield conn
    finally:
        conn.close()


def get_cursor() -> Generator[DictCursor, None, None]:
    """FastAPI dependency for database cursor with transaction handling."""
    with get_connection() as conn:
        cursor = conn.cursor(DictCursor)
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
