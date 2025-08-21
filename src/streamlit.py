# dashboard.py
import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import text, inspect
from utils.utils import get_db_engine

load_dotenv()
DB_TABLE = os.getenv("DB_TABLE")
DB_SCHEMA = os.getenv("DB_SCHEMA", "public")  # set this in .env if you use a non-public schema

def main():
    st.title("DC Freshwater fish Customer Orders")

    orders_df = get_data_from_db()

    st.write(orders_df)


def get_data_from_db():
        engine = get_db_engine()

        df = pd.read_sql_table(DB_TABLE, con=engine, schema=DB_SCHEMA)
        return df
    
if __name__ == "__main__":
    main()