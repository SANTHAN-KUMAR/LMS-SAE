"""Quick script to update subject mappings with correct assignment IDs"""
import asyncio
from app.db.database import async_session_maker
from app.db.models import SubjectMapping
from sqlalchemy import select, update

async def update_mappings():
    async with async_session_maker() as db:
        # Show before
        result = await db.execute(
            select(SubjectMapping).where(
                SubjectMapping.subject_code.in_(['19AI405', '19AI411'])
            )
        )
        mappings = result.scalars().all()
        print("BEFORE:")
        for m in mappings:
            print(f"  {m.subject_code}: Course {m.moodle_course_id}, Assignment {m.moodle_assignment_id}")
        print()
        
        # Update 19AI405
        await db.execute(
            update(SubjectMapping)
            .where(SubjectMapping.subject_code == '19AI405')
            .values(
                moodle_course_id=3,
                moodle_assignment_id=2,
                moodle_assignment_name='PART B and C ANSWER SCRIPT'
            )
        )
        
        # Update 19AI411
        await db.execute(
            update(SubjectMapping)
            .where(SubjectMapping.subject_code == '19AI411')
            .values(
                moodle_course_id=4,
                moodle_assignment_id=3,
                moodle_assignment_name='PART B and C ANSWER SCRIPT'
            )
        )
        
        await db.commit()
        
        # Show after
        result = await db.execute(
            select(SubjectMapping).where(
                SubjectMapping.subject_code.in_(['19AI405', '19AI411'])
            )
        )
        mappings = result.scalars().all()
        print("AFTER:")
        for m in mappings:
            print(f"  {m.subject_code}: Course {m.moodle_course_id}, Assignment {m.moodle_assignment_id}")
        print()
        print("Database updated successfully!")

if __name__ == "__main__":
    asyncio.run(update_mappings())

