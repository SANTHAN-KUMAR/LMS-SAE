"""
Script to discover Moodle assignment instance IDs and generate SQL UPDATE statements.

Usage:
    python discover_assignments_sql.py <student_username> <student_password>
    
This will output SQL statements you can run directly in PostgreSQL.
"""

import asyncio
import sys
import os
from app.services.moodle_client import MoodleClient
from app.core.config import settings

async def discover_and_generate_sql():
    """Discover assignment IDs and generate SQL"""
    
    if len(sys.argv) < 3:
        print("ERROR: Please provide student username and password")
        print("Usage: python discover_assignments_sql.py <username> <password>")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    
    print("=" * 60)
    print("Moodle Assignment Discovery - SQL Generator")
    print("=" * 60)
    print(f"Base URL: {settings.moodle_base_url}")
    print(f"Student: {username}")
    print()
    
    client = MoodleClient()
    
    try:
        # Authenticate
        print("Authenticating with Moodle...")
        token_response = await client.get_token(username=username, password=password)
        token = token_response["token"]
        client.token = token
        
        site_info = await client.get_site_info(token=token)
        print(f"✓ Authenticated as: {site_info.get('fullname')}")
        print()
        
        # Get assignments for courses 3 and 4
        print("Discovering assignments...")
        assignments_result = await client.get_assignments(course_ids=[3, 4])
        courses_data = assignments_result.get("courses", [])
        
        print(f"✓ Found {len(courses_data)} courses")
        print()
        
        # Find the assignments we need
        sql_statements = []
        
        for course in courses_data:
            course_id = course.get("id")
            course_name = course.get("fullname", f"Course {course_id}")
            assignments = course.get("assignments", [])
            
            print(f"Course {course_id}: {course_name}")
            
            for assignment in assignments:
                assignment_id = assignment.get("id")
                cmid = assignment.get("cmid")
                assignment_name = assignment.get("name", "Unknown")
                
                print(f"  Assignment: {assignment_name}")
                print(f"    Instance ID: {assignment_id}, CMID: {cmid}")
                
                # Match based on cmid from URLs
                if course_id == 3 and cmid == 4:
                    # 19AI405
                    sql_statements.append({
                        "subject_code": "19AI405",
                        "course_id": 3,
                        "assignment_id": assignment_id,
                        "assignment_name": assignment_name
                    })
                elif course_id == 4 and cmid == 6:
                    # 19AI411
                    sql_statements.append({
                        "subject_code": "19AI411",
                        "course_id": 4,
                        "assignment_id": assignment_id,
                        "assignment_name": assignment_name
                    })
        
        print()
        print("=" * 60)
        print("SQL UPDATE STATEMENTS")
        print("=" * 60)
        print()
        print("-- Run these SQL statements in your PostgreSQL database:")
        print()
        
        for mapping in sql_statements:
            sql = f"""UPDATE subject_mappings
SET moodle_course_id = {mapping['course_id']},
    moodle_assignment_id = {mapping['assignment_id']},
    moodle_assignment_name = '{mapping['assignment_name'].replace("'", "''")}',
    updated_at = NOW()
WHERE subject_code = '{mapping['subject_code']}' AND is_active = true;"""
            
            print(sql)
            print()
        
        print("-- Verify the updates:")
        print("SELECT subject_code, moodle_course_id, moodle_assignment_id, moodle_assignment_name")
        print("FROM subject_mappings")
        print("WHERE subject_code IN ('19AI405', '19AI411');")
        print()
        
        if sql_statements:
            print("=" * 60)
            print("✓ Discovery completed! Copy and run the SQL statements above.")
            print("=" * 60)
        else:
            print("ERROR: Could not find matching assignments!")
            print("Please verify the Course Module IDs in your Moodle URLs.")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(discover_and_generate_sql())

