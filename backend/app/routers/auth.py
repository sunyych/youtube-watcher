"""Authentication routes"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
import bcrypt
from typing import Optional
from app.config import settings
from app.database import get_db
from app.models.database import User

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str


class AuthConfigResponse(BaseModel):
    allow_registration: bool


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


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password using bcrypt directly to avoid passlib initialization issues"""
    try:
        # Truncate password to 72 bytes
        password_bytes = _truncate_password(plain_password)
        # Use bcrypt directly to avoid passlib's initialization issues
        return bcrypt.checkpw(password_bytes, hashed_password.encode('utf-8'))
    except Exception:
        # Fallback to passlib if bcrypt fails
        password_bytes = _truncate_password(plain_password)
        plain_password = password_bytes.decode('utf-8', errors='ignore')
        return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash password using bcrypt directly to avoid passlib initialization issues"""
    try:
        # Truncate password to 72 bytes
        password_bytes = _truncate_password(password)
        # Use bcrypt directly to avoid passlib's initialization issues
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode('utf-8')
    except Exception:
        # Fallback to passlib if bcrypt fails
        password_bytes = _truncate_password(password)
        password = password_bytes.decode('utf-8', errors='ignore')
        return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta = None):
    """Create JWT token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


@router.post("/register", response_model=LoginResponse)
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user"""
    if not settings.allow_registration:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is disabled"
        )

    # Check if username already exists
    existing_user = db.query(User).filter(User.username == request.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    # Create new user
    hashed_password = get_password_hash(request.password)
    user = User(
        username=request.username,
        hashed_password=hashed_password
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    # Create access token
    access_token = create_access_token(data={"sub": str(user.id), "username": user.username})
    return LoginResponse(
        access_token=access_token,
        user_id=user.id,
        username=user.username
    )


@router.get("/config", response_model=AuthConfigResponse)
async def get_auth_config():
    """Expose auth-related configuration to frontend."""
    return AuthConfigResponse(allow_registration=settings.allow_registration)


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Login with username and password"""
    # Find user by username
    user = db.query(User).filter(User.username == request.username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # Verify password
    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # Create access token
    access_token = create_access_token(data={"sub": str(user.id), "username": user.username})
    return LoginResponse(
        access_token=access_token,
        user_id=user.id,
        username=user.username
    )


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """Get current authenticated user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        
        # Get user from database
        user = db.query(User).filter(User.id == int(user_id)).first()
        if user is None:
            raise credentials_exception
        return user
    except (JWTError, ValueError, TypeError):
        raise credentials_exception


class ChangeUsernameRequest(BaseModel):
    new_username: str


class UserProfileResponse(BaseModel):
    user_id: int
    username: str
    summary_language: str
    show_feedback_button: bool


class UpdateSummaryLanguageRequest(BaseModel):
    summary_language: str


class UpdateFeedbackButtonRequest(BaseModel):
    show_feedback_button: bool


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(user: User = Depends(get_current_user)):
    """Get current user profile including summary language and feedback button preference."""
    return UserProfileResponse(
        user_id=user.id,
        username=user.username,
        summary_language=user.summary_language or "中文",
        show_feedback_button=getattr(user, "show_feedback_button", True),
    )


@router.patch("/settings/summary-language")
async def update_summary_language(
    request: UpdateSummaryLanguageRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update user's preferred summary language (e.g. 中文, English)."""
    lang = (request.summary_language or "中文").strip()
    user.summary_language = lang
    db.commit()
    db.refresh(user)
    return {"summary_language": user.summary_language}


@router.patch("/settings/feedback-button")
async def update_feedback_button(
    request: UpdateFeedbackButtonRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update whether to show the floating feedback button on the frontend."""
    user.show_feedback_button = request.show_feedback_button
    db.commit()
    db.refresh(user)
    return {"show_feedback_button": user.show_feedback_button}


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change password for the current user"""
    # Verify old password
    if not verify_password(request.old_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect old password"
        )
    
    # Update password
    user.hashed_password = get_password_hash(request.new_password)
    db.commit()
    db.refresh(user)
    
    return {"message": "Password changed successfully"}


@router.post("/change-username")
async def change_username(
    request: ChangeUsernameRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Change username for the current user"""
    new_username = request.new_username.strip()
    
    # Validate new username
    if not new_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username cannot be empty"
        )
    
    if len(new_username) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username must be at least 3 characters long"
        )
    
    # Check if new username already exists
    existing_user = db.query(User).filter(User.username == new_username).first()
    if existing_user and existing_user.id != user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    
    # Update username
    old_username = user.username
    user.username = new_username
    db.commit()
    db.refresh(user)
    
    return {
        "message": "Username changed successfully",
        "old_username": old_username,
        "new_username": user.username
    }
