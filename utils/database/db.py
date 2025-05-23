from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import dotenv

dotenv.load_dotenv()

ENV = os.getenv("TRADING_ENV")

# Load environment variables
DATABASE_USER = os.getenv("TRADING_POSTGRES_USER")
DATABASE_PASSWORD = os.getenv("TRADING_POSTGRES_PASSWORD")
DATABASE_HOST = os.getenv(f"TRADING_POSTGRES_HOST_{ENV}")
DATABASE_PORT = os.getenv(f"TRADING_POSTGRES_PORT_{ENV}")
DATABASE_DB = os.getenv("TRADING_POSTGRES_DB")


DATABASE_URL = f"postgresql+psycopg2://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_DB}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)