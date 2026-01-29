"""Database connection and session management"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.models.database import Base, User, VideoRecord
from app.config import settings
import bcrypt
import logging

def _truncate_password(password: str) -> bytes:
    """Truncate password to 72 bytes for bcrypt compatibility"""
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        # Truncate to 72 bytes, handling UTF-8 character boundaries
        truncated = password_bytes[:72]
        # Remove any incomplete UTF-8 sequences at the end
        while truncated and truncated[-1] & 0xC0 == 0x80:
            truncated = truncated[:-1]
        return truncated
    return password_bytes

def get_password_hash(password: str) -> str:
    """Hash password using bcrypt directly to avoid passlib initialization issues"""
    try:
        # Truncate password to 72 bytes
        password_bytes = _truncate_password(password)
        # Use bcrypt directly to avoid passlib's initialization issues
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode('utf-8')
    except Exception as e:
        logger.error(f"Error hashing password with bcrypt: {e}")
        # If bcrypt fails, raise the error
        raise

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables, run migrations, and create default user"""
    # Create tables that don't exist yet (no-op for existing tables)
    Base.metadata.create_all(bind=engine)
    # Run migrations to add missing columns / tables on existing DBs
    from app.migrations.runner import run_migrations
    run_migrations(engine)

    # Create default user if it doesn't exist
    db = SessionLocal()
    try:
        # Check if any users exist
        user_count = db.query(User).count()
        if user_count == 0:
            # Create default user with the configured password
            default_user = User(
                username="admin",
                hashed_password=get_password_hash(settings.web_password)
            )
            db.add(default_user)
            db.commit()
            logger.info("Created default user 'admin'")
        
        # Migrate existing video records to default user if they don't have user_id
        records_without_user = db.query(VideoRecord).filter(VideoRecord.user_id.is_(None)).all()
        if records_without_user:
            default_user = db.query(User).filter(User.username == "admin").first()
            if default_user:
                for record in records_without_user:
                    record.user_id = default_user.id
                db.commit()
                logger.info(f"Migrated {len(records_without_user)} video records to default user")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        db.rollback()
    finally:
        db.close()
