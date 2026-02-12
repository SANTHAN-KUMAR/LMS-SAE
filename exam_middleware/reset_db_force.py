
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text, inspect
from app.db.database import engine, Base
from init_db import create_tables, seed_staff_user, seed_subject_mappings, seed_system_config, verify_database

async def reset_database():
    print("=" * 60)
    print("  ⚠ WARNING: PREPARING TO WIPE DATABASE (AGGRESSIVE MODE)")
    print("=" * 60)
    print("  This will:")
    print("  1. Discover ALL tables in the database (including manually created ones)")
    print("  2. DROP ALL tables found")
    print("  3. Re-create schema from application models")
    print("  4. Seed default admin user and config")
    print("  ALL EXISTING DATA WILL BE LOST FOREVER.")
    print("=" * 60)
    
    confirm = input("Are you sure you want to proceed? (Type 'yes' to confirm): ")
    
    if confirm.lower() != 'yes':
        print("Operation cancelled.")
        return

    print("\n1. Inspecting database for tables...")
    try:
        async with engine.begin() as conn:
            # We need to run reflection in a sync context within the async connection
            def get_all_tables(connection):
                inspector = inspect(connection)
                return inspector.get_table_names()

            tables = await conn.run_sync(get_all_tables)
            
        if not tables:
            print("✓ No tables found in database.")
        else:
            print(f"✓ Found {len(tables)} tables: {', '.join(tables)}")
            print("\n2. Dropping all tables...")
            
            async with engine.begin() as conn:
                # Disable foreign key checks temporarily to allow dropping in any order
                await conn.execute(text("DROP SCHEMA public CASCADE;"))
                await conn.execute(text("CREATE SCHEMA public;"))
                # await conn.execute(text("GRANT ALL ON SCHEMA public TO postgres;")) 
                # Note: valid for postgres, might need adjustment if user role is different
            
            print("✓ Schema 'public' recreated (effectively dropping all tables).")

    except Exception as e:
        print(f"✗ Error wiping database: {e}")
        return

    print("\n3. Re-creating tables...")
    await create_tables()
    
    print("\n4. Seeding default data...")
    await seed_staff_user()
    await seed_subject_mappings()
    await seed_system_config()
    
    print("\n5. Verifying...")
    await verify_database()

    print("\n" + "=" * 60)
    print("  Database RESET Complete.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(reset_database())
