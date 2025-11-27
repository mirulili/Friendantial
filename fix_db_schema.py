import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("Error: DATABASE_URL is not set.")
    sys.exit(1)

def fix_schema():
    print(f"Connecting to database...")
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as connection:
        # Check if column exists
        check_sql = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='recommendation_runs' AND column_name='report';
        """)
        result = connection.execute(check_sql)
        if result.fetchone():
            print("Column 'report' already exists in 'recommendation_runs'.")
            return

        print("Column 'report' missing. Adding it...")
        try:
            # Add column
            alter_sql = text("ALTER TABLE recommendation_runs ADD COLUMN report TEXT;")
            connection.execute(alter_sql)
            connection.commit()
            print("Successfully added column 'report' to 'recommendation_runs'.")
        except Exception as e:
            print(f"Failed to add column: {e}")
            sys.exit(1)

if __name__ == "__main__":
    fix_schema()
