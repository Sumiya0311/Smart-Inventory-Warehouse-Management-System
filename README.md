Smart Inventory & Warehouse Management System

Project Overview

The Smart Inventory & Warehouse Management System is a backend application developed using FastAPI and MySQL to manage warehouse operations, inventory, purchases, sales, and returns through REST APIs.

Technologies Used

- Python
- FastAPI
- Pydantic
- SQLAlchemy ORM
- MySQL
- Alembic
- JWT Authentication
- Pytest
- SMTP Email Notifications
- Uvicorn

Key Features

- User authentication and role-based access control
- Warehouse, category, and product management
- Supplier and purchase order management
- Customer and sales order management
- Inventory tracking and stock movements
- Sales order dispatch and return/refund workflows
- Low-stock email notifications
- Audit logs and reporting APIs
- Input validation and HTTP error handling
- Database migrations using Alembic

Project Structure

Smart-Inventory-Warehouse-Management-System/
├── alembic/
├── app/
│   ├── routers/
│   ├── schemas/
│   └── main.py
├── screenshots/
├── .env.example
├── .gitignore
├── alembic.ini
├── create_admin.py
├── requirements.txt
├── smart-inventory.sql
└── README.md

Prerequisites

- Python 3.10 or a compatible version for the project dependencies
- MySQL Server
- Git

Installation and Setup

1. Clone the repository

git clone https://github.com/Sumiya0311/Smart-Inventory-Warehouse-Management-System.git
cd Smart-Inventory-Warehouse-Management-System

2. Create and activate a virtual environment

Windows:

python -m venv venv
.\venv\Scripts\Activate.ps1

3. Install dependencies

pip install -r requirements.txt

4. Configure the database

- Create a MySQL database.
- Configure the database connection and other required environment variables using ".env.example" as a reference.
- Add your own local database credentials and secret values to ".env".
- Do not commit ".env" or real credentials to GitHub.

5. Apply database migrations

alembic upgrade head

6. Create an administrator

Configure the required environment variables first, then run:

python create_admin.py

7. Start the application

uvicorn app.main:app --reload

API Documentation

After starting the application, open:

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

Use the API documentation to test the available endpoints. Authenticated endpoints may require a valid access token and the appropriate user role.

Testing

Run the available automated tests with:

pytest

Screenshots

The "screenshots/" directory contains project screenshots demonstrating selected API operations and application workflows.

Security

- Keep database passwords, JWT secrets, and SMTP credentials in environment variables.
- Do not upload ".env" or real credentials.
- Use appropriate roles and authentication when accessing protected endpoints.

Author

Sumiya Shaik

Repository

https://github.com/Sumiya0311/Smart-Inventory-Warehouse-Management-System