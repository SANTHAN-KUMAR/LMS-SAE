import os
from app.services.file_processor import FileProcessor


def test_parse_filename_strict():
    fp = FileProcessor(upload_dir=os.path.join(os.getcwd(), "uploads", "temp_tests"))
    reg, subj, ok = fp.parse_filename("212223240065_19AI405.pdf")
    assert ok and reg == "212223240065" and subj == "19AI405"


def test_parse_filename_flexible():
    fp = FileProcessor(upload_dir=os.path.join(os.getcwd(), "uploads", "temp_tests"))
    reg, subj, ok = fp.parse_filename("21222324065-AI405A.JPG")
    assert ok and len(reg) == 12 and reg.isdigit() and subj == "AI405A"


def test_validate_file_happy_path():
    fp = FileProcessor(upload_dir=os.path.join(os.getcwd(), "uploads", "temp_tests"))
    content = b"%PDF-1.4 minimal"
    ok, msg, meta = fp.validate_file(content, "212223240065_19AI405.pdf")
    assert ok and meta["size_bytes"] == len(content)


def test_validate_file_reject_large_and_bad_extension(monkeypatch):
    fp = FileProcessor(upload_dir=os.path.join(os.getcwd(), "uploads", "temp_tests"))
    # Force a low max size
    from app.core import config
    monkeypatch.setenv("MAX_FILE_SIZE_MB", "1")
    monkeypatch.setenv("ALLOWED_EXTENSIONS", ".pdf,.jpg")
    # Reload settings
    monkeypatch.setenv("UPLOAD_DIR", fp.upload_dir)
    # Large content
    content = b"x" * (2 * 1024 * 1024)
    ok, msg, meta = fp.validate_file(content, "bad.txt")
    assert ok is False
    assert "File too large" in msg or "Invalid file type" in msg
