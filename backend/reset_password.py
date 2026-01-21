#!/usr/bin/env python3
"""Reset password command-line tool"""
import sys
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import init_db, SessionLocal
from app.models.database import User
from app.routers.auth import get_password_hash
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def reset_password(username: str, new_password: str):
    """Reset password for a user"""
    db = SessionLocal()
    try:
        # Find user
        user = db.query(User).filter(User.username == username).first()
        if not user:
            logger.error(f"User '{username}' not found")
            return False
        
        # Update password
        user.hashed_password = get_password_hash(new_password)
        db.commit()
        
        logger.info(f"Password reset successfully for user '{username}'")
        return True
    except Exception as e:
        logger.error(f"Error resetting password: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def list_users():
    """List all users"""
    db = SessionLocal()
    try:
        users = db.query(User).all()
        if not users:
            print("No users found")
            return
        
        print("\nUsers:")
        print("-" * 50)
        for user in users:
            print(f"  ID: {user.id}, Username: {user.username}, Created: {user.created_at}")
        print("-" * 50)
    except Exception as e:
        logger.error(f"Error listing users: {e}")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Reset password for a user",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Reset password for a user
  python reset_password.py --username admin --new-password newpass123
  
  # List all users
  python reset_password.py --list-users
  
  # Interactive mode (will prompt for username and password)
  python reset_password.py --interactive
        """
    )
    
    parser.add_argument(
        "--username", "-u",
        type=str,
        help="Username to reset password for"
    )
    
    parser.add_argument(
        "--new-password", "-p",
        type=str,
        help="New password"
    )
    
    parser.add_argument(
        "--list-users", "-l",
        action="store_true",
        help="List all users"
    )
    
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Interactive mode (prompt for username and password)"
    )
    
    args = parser.parse_args()
    
    # Initialize database
    init_db()
    
    # List users if requested
    if args.list_users:
        list_users()
        return
    
    # Interactive mode
    if args.interactive:
        username = input("Enter username: ").strip()
        if not username:
            print("Error: Username cannot be empty")
            sys.exit(1)
        
        import getpass
        new_password = getpass.getpass("Enter new password: ")
        if not new_password:
            print("Error: Password cannot be empty")
            sys.exit(1)
        
        confirm_password = getpass.getpass("Confirm new password: ")
        if new_password != confirm_password:
            print("Error: Passwords do not match")
            sys.exit(1)
        
        if reset_password(username, new_password):
            print(f"\n✓ Password reset successfully for user '{username}'")
            sys.exit(0)
        else:
            print(f"\n✗ Failed to reset password for user '{username}'")
            sys.exit(1)
    
    # Command-line mode
    if not args.username or not args.new_password:
        parser.print_help()
        sys.exit(1)
    
    if reset_password(args.username, args.new_password):
        print(f"✓ Password reset successfully for user '{args.username}'")
        sys.exit(0)
    else:
        print(f"✗ Failed to reset password for user '{args.username}'")
        sys.exit(1)


if __name__ == "__main__":
    main()
