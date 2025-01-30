import os
import tempfile
import shutil
import atexit
import sqlmodel

# In-memory path for the temp directory
temp_dir_path = None

def get_temp_dir() -> str:
    global temp_dir_path
    if not temp_dir_path:
        temp_dir_path = tempfile.mkdtemp()
    return temp_dir_path

def cleanup_temp_dir() -> None:
    global temp_dir_path
    if temp_dir_path and os.path.exists(temp_dir_path):
        shutil.rmtree(temp_dir_path)
        temp_dir_path = None

# Register cleanup function
atexit.register(cleanup_temp_dir)

def get_db_session() -> sqlmodel.Session:
    engine = sqlmodel.create_engine("sqlite:///x_automation_studio.db")
    return sqlmodel.Session(engine)
