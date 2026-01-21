#!/usr/bin/env python3
"""Change username command-line tool"""
import sys
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import init_db, SessionLocal
from app.models.database import User
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def change_username(old_username: str, new_username: str):
    """Change username for a user"""
    db = SessionLocal()
    try:
        # Find user by old username
        user = db.query(User).filter(User.username == old_username).first()
        if not user:
            logger.error(f"User '{old_username}' not found")
            return False
        
        # Check if new username already exists
        existing_user = db.query(User).filter(User.username == new_username).first()
        if existing_user:
            logger.error(f"Username '{new_username}' already exists")
            return False
        
        # Validate new username
        if not new_username or not new_username.strip():
            logger.error("New username cannot be empty")
            return False
        
        new_username = new_username.strip()
        if len(new_username) < 3:
            logger.error("New username must be at least 3 characters long")
            return False
        
        # Update username
        old_username_value = user.username
        user.username = new_username
        db.commit()
        
        logger.info(f"Username changed successfully from '{old_username_value}' to '{new_username}'")
        return True
    except Exception as e:
        logger.error(f"Error changing username: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def change_username_by_id(user_id: int, new_username: str):
    """Change username for a user by ID"""
    db = SessionLocal()
    try:
        # Find user by ID
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"User with ID {user_id} not found")
            return False
        
        # Check if new username already exists
        existing_user = db.query(User).filter(User.username == new_username).first()
        if existing_user:
            logger.error(f"Username '{new_username}' already exists")
            return False
        
        # Validate new username
        if not new_username or not new_username.strip():
            logger.error("New username cannot be empty")
            return False
        
        new_username = new_username.strip()
        if len(new_username) < 3:
            logger.error("New username must be at least 3 characters long")
            return False
        
        # Update username
        old_username_value = user.username
        user.username = new_username
        db.commit()
        
        logger.info(f"Username changed successfully from '{old_username_value}' to '{new_username}' for user ID {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error changing username: {e}")
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
        description="Change username for a user",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Change username by old username
  python change_username.py --old-username admin --new-username newadmin
  
  # Change username by user ID
  python change_username.py --user-id 1 --new-username newadmin
  
  # List all users
  python change_username.py --list-users
  
  # Interactive mode (will prompt for old username and new username)
  python change_username.py --interactive
        """
    )
    
    parser.add_argument(
        "--old-username", "-o",
        type=str,
        help="Old username to change"
    )
    
    parser.add_argument(
        "--user-id", "-i",
        type=int,
        help="User ID to change username for"
    )
    
    parser.add_argument(
        "--new-username", "-n",
        type=str,
        help="New username"
    )
    
    parser.add_argument(
        "--list-users", "-l",
        action="store_true",
        help="List all users"
    )
    
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive mode (prompt for old username and new username)"
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
        old_username = input("Enter old username: ").strip()
        if not old_username:
            print("Error: Old username cannot be empty")
            sys.exit(1)
        
        new_username = input("Enter new username: ").strip()
        if not new_username:
            print("Error: New username cannot be empty")
            sys.exit(1)
        
        if len(new_username) < 3:
            print("Error: New username must be at least 3 characters long")
            sys.exit(1)
        
        confirm = input(f"Confirm changing username from '{old_username}' to '{new_username}'? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("Cancelled")
            sys.exit(0)
        
        if change_username(old_username, new_username):
            print(f"\n✓ Username changed successfully from '{old_username}' to '{new_username}'")
            sys.exit(0)
        else:
            print(f"\n✗ Failed to change username from '{old_username}' to '{new_username}'")
            sys.exit(1)
    
    # Command-line mode
    if not args.new_username:
        parser.print_help()
        sys.exit(1)
    
    if args.user_id:
        # Change by user ID
        if change_username_by_id(args.user_id, args.new_username):
            print(f"✓ Username changed successfully for user ID {args.user_id}")
            sys.exit(0)
        else:
            print(f"✗ Failed to change username for user ID {args.user_id}")
            sys.exit(1)
    elif args.old_username:
        # Change by old username
        if change_username(args.old_username, args.new_username):
            print(f"✓ Username changed successfully from '{args.old_username}' to '{args.new_username}'")
            sys.exit(0)
        else:
            print(f"✗ Failed to change username from '{args.old_username}' to '{args.new_username}'")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
