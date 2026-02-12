
import asyncio
from sqlalchemy import text
from app.db.database import engine

async def check_tables():
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """))
        tables = [row[0] for row in result.fetchall()]
        
        print(f"Found {len(tables)} tables: {', '.join(tables)}")
        
        if "playing_with_neon" in tables:
            print("❌ FAIL: 'playing_with_neon' table still exists!")
        else:
            print("✓ SUCCESS: 'playing_with_neon' table is GONE.")

if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    asyncio.run(check_tables())
