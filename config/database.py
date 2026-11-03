from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

DATABASE_URL = "mysql+pymysql://thyfelow:sage@localhost:3306/iot_system"

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

class Base(DeclarativeBase):
    pass

def init_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()