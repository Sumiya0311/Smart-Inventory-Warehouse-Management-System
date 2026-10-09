from getpass import getpass

from app.auth.security import hash_password
from app.database import SessionLocal
from app.models.user import User


def main():
    db = SessionLocal()

    try:
        existing_admin = db.query(User).filter(
            User.role == "Admin"
        ).first()

        if existing_admin:
            print("Admin already exists.")
            return

        full_name = input("Admin name: ").strip()
        email = input("Admin email: ").strip()
        password = getpass("Admin password: ")

        admin = User(
            full_name=full_name,
            email=email,
            password_hash=hash_password(password),
            role="Admin",
            is_active=True,
            created_by=None
        )

        db.add(admin)
        db.commit()

        print("Admin created successfully.")

    finally:
        db.close()


if __name__ == "__main__":
    main()