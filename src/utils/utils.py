import os
from dotenv import load_dotenv
from sqlalchemy import create_engine

def get_db_engine():
    # load .env database creds
    load_dotenv()
    
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASS")
    db_host = os.getenv("DB_HOST")
    db_port = os.getenv("DB_PORT")
    db_name = os.getenv("DB_NAME")

    db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    return create_engine(db_url)