import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def list_tables():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL environment variable not set.")
        return

    try:
        engine = create_async_engine(database_url)
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            )
            tables = [row[0] for row in result.fetchall()]
            
            if tables:
                print("\n✅ Connection Successful!")
                print(f"Found {len(tables)} tables in the database:")
                for table in tables:
                    print(f" - {table}")
            else:
                print("\n✅ Connection Successful, but no tables found (database is empty).")
        
        await engine.dispose()
        
    except Exception as e:
        print(f"\n❌ Connection Failed: {e}")

if __name__ == "__main__":
    asyncio.run(list_tables())
