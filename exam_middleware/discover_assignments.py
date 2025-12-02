"""
Script to discover Moodle assignment instance IDs from Course Module IDs
and update the subject_mappings table with correct values.

Usage:
    python discover_assignments.py <student_username> <student_password>
    
Or set MOODLE_STUDENT_USERNAME and MOODLE_STUDENT_PASSWORD environment variables.
"""

import asyncio
import sys
import os
from app.services.moodle_client import MoodleClient
from app.db.database import async_session_maker
from app.db.models import SubjectMapping
from sqlalchemy import select, update
from app.core.config import settings

async def discover_and_update():
    """Discover assignment IDs and update database"""
    
    # Get credentials from args or env
    if len(sys.argv) >= 3:
        username = sys.argv[1]
        password = sys.argv[2]
    else:
        username = os.getenv("MOODLE_STUDENT_USERNAME", "student2")
        password = os.getenv("MOODLE_STUDENT_PASSWORD", "")
        if not password:
            print("ERROR: Please provide student username and password")
            print("Usage: python discover_assignments.py <username> <password>")
            sys.exit(1)
    
    print("=" * 60)
    print("Moodle Assignment Discovery Script")
    print("=" * 60)
    print(f"Base URL: {settings.moodle_base_url}")
    print(f"Student: {username}")
    print()
    
    client = MoodleClient()
    
    try:
        # Step 1: Authenticate
        print("Step 1: Authenticating with Moodle...")
        token_response = await client.get_token(username=username, password=password)
        token = token_response["token"]
        client.token = token
        
        site_info = await client.get_site_info(token=token)
        print(f"✓ Authenticated as: {site_info.get('fullname')} (ID: {site_info.get('userid')})")
        print()
        
        # Step 2: Get assignments for courses 3 and 4
        print("Step 2: Discovering assignments in courses 3 and 4...")
        assignments_result = await client.get_assignments(course_ids=[3, 4])
        
        # Parse the response
        courses_data = assignments_result.get("courses", [])
        
        print(f"✓ Found {len(courses_data)} courses")
        print()
        
        # Map of course_id -> list of assignments
        course_assignments = {}
        
        for course in courses_data:
            course_id = course.get("id")
            course_name = course.get("fullname", f"Course {course_id}")
            assignments = course.get("assignments", [])
            
            print(f"Course {course_id}: {course_name}")
            print(f"  Found {len(assignments)} assignments:")
            
            course_assignments[course_id] = []
            
            for assignment in assignments:
                assignment_id = assignment.get("id")  # This is the assignment instance ID
                cmid = assignment.get("cmid")  # This is the course module ID (from URL)
                assignment_name = assignment.get("name", "Unknown")
                
                print(f"    - {assignment_name}")
                print(f"      Assignment Instance ID: {assignment_id}")
                print(f"      Course Module ID (cmid): {cmid}")
                
                course_assignments[course_id].append({
                    "instance_id": assignment_id,
                    "cmid": cmid,
                    "name": assignment_name
                })
            
            print()
        
        # Step 3: Match cmid values to find correct assignment instance IDs
        print("Step 3: Matching Course Module IDs to Assignment Instance IDs...")
        print()
        
        # Expected mappings based on URLs provided:
        # Course 3 (19AI405): cmid=4 -> need assignment instance ID
        # Course 4 (19AI411): cmid=6 -> need assignment instance ID
        
        mappings_to_update = []
        
        # Find assignment for course 3 with cmid=4
        if 3 in course_assignments:
            for assignment in course_assignments[3]:
                if assignment["cmid"] == 4:
                    mappings_to_update.append({
                        "subject_code": "19AI405",
                        "course_id": 3,
                        "assignment_instance_id": assignment["instance_id"],
                        "assignment_name": assignment["name"],
                        "cmid": 4
                    })
                    print(f"✓ Found 19AI405:")
                    print(f"    Course ID: 3")
                    print(f"    Course Module ID (cmid): 4")
                    print(f"    Assignment Instance ID: {assignment['instance_id']}")
                    print(f"    Assignment Name: {assignment['name']}")
                    print()
                    break
        
        # Find assignment for course 4 with cmid=6
        if 4 in course_assignments:
            for assignment in course_assignments[4]:
                if assignment["cmid"] == 6:
                    mappings_to_update.append({
                        "subject_code": "19AI411",
                        "course_id": 4,
                        "assignment_instance_id": assignment["instance_id"],
                        "assignment_name": assignment["name"],
                        "cmid": 6
                    })
                    print(f"✓ Found 19AI411:")
                    print(f"    Course ID: 4")
                    print(f"    Course Module ID (cmid): 6")
                    print(f"    Assignment Instance ID: {assignment['instance_id']}")
                    print(f"    Assignment Name: {assignment['name']}")
                    print()
                    break
        
        if not mappings_to_update:
            print("ERROR: Could not find matching assignments!")
            print("Please verify the Course Module IDs in your Moodle URLs.")
            return
        
        # Step 4: Update database
        print("Step 4: Updating database...")
        async with async_session_maker() as db:
            for mapping in mappings_to_update:
                # Find existing mapping
                result = await db.execute(
                    select(SubjectMapping).where(
                        SubjectMapping.subject_code == mapping["subject_code"]
                    )
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    # Update existing
                    existing.moodle_course_id = mapping["course_id"]
                    existing.moodle_assignment_id = mapping["assignment_instance_id"]
                    existing.moodle_assignment_name = mapping["assignment_name"]
                    await db.commit()
                    print(f"✓ Updated {mapping['subject_code']}:")
                    print(f"    Course ID: {mapping['course_id']}")
                    print(f"    Assignment Instance ID: {mapping['assignment_instance_id']} (was {existing.moodle_assignment_id})")
                else:
                    # Create new
                    new_mapping = SubjectMapping(
                        subject_code=mapping["subject_code"],
                        moodle_course_id=mapping["course_id"],
                        moodle_assignment_id=mapping["assignment_instance_id"],
                        moodle_assignment_name=mapping["assignment_name"],
                        is_active=True
                    )
                    db.add(new_mapping)
                    await db.commit()
                    print(f"✓ Created {mapping['subject_code']}:")
                    print(f"    Course ID: {mapping['course_id']}")
                    print(f"    Assignment Instance ID: {mapping['assignment_instance_id']}")
        
        print()
        print("=" * 60)
        print("✓ Discovery and update completed successfully!")
        print("=" * 60)
        print()
        print("Updated mappings:")
        async with async_session_maker() as db:
            result = await db.execute(
                select(SubjectMapping).where(
                    SubjectMapping.subject_code.in_(["19AI405", "19AI411"])
                )
            )
            mappings = result.scalars().all()
            for m in mappings:
                print(f"  {m.subject_code}: Course {m.moodle_course_id}, Assignment {m.moodle_assignment_id}")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(discover_and_update())

