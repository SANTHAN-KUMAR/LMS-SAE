"""Reset artifact for testing"""
from sqlalchemy import create_engine, text

# Password from .env DATABASE_URL
engine = create_engine("postgresql://postgres:3373@localhost:5432/exam_middleware")

with engine.connect() as conn:
    result = conn.execute(text("""
        UPDATE examination_artifacts 
        SET workflow_status='PENDING', 
            moodle_draft_item_id=NULL, 
            moodle_submission_id=NULL, 
            lms_transaction_id=NULL, 
            submit_timestamp=NULL, 
            completed_at=NULL, 
            error_message=NULL 
        WHERE parsed_reg_no='212223240065' 
        RETURNING id, artifact_uuid, workflow_status
    """))
    conn.commit()
    for row in result:
        print(f"Reset artifact: id={row[0]}, uuid={row[1]}, status={row[2]}")
