#!/usr/bin/env python3
"""Verify Snowflake connection works with current configuration."""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from deployment_queue.database import get_connection


def main():
    print("Testing Snowflake connection...")
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE()")
            user, role, warehouse = cursor.fetchone()
            print("✓ Connected successfully")
            print(f"  User: {user}")
            print(f"  Role: {role}")
            print(f"  Warehouse: {warehouse}")

            # Test table access
            cursor.execute("SHOW TABLES LIKE 'DEPLOYMENTS'")
            if cursor.fetchone():
                print("✓ Deployments table exists")
            else:
                print("⚠ Deployments table not found - run sql/schema.sql")

    except Exception as e:
        print(f"✗ Connection failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
