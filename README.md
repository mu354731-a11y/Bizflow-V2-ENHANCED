
# BizFlow V2

A small-business management MVP built with Python and Streamlit.

## Features

- Signup and login
- Separate workspace for each business
- Password hashing
- Staff accounts and role options
- Customer management
- Products and stock tracking
- Invoice creation and PDF downloads
- Partial and full payment tracking
- Expense management
- Sales and estimated profit analytics
- Business profile and currency settings
- WhatsApp invoice reminder links
- CSV exports

## Run on Windows

Open CMD inside this folder and run:

    py -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    .venv\Scripts\python.exe -m streamlit run app.py

Open the local URL shown by Streamlit.

Create your business account on the signup tab.

## Cloud deployment

Upload app.py, database.py, auth.py, requirements.txt,
README.md and .gitignore to your GitHub repository.

Set the Streamlit main file path to app.py.

Configure DATABASE_URL with your managed PostgreSQL
connection string before deploying.

Do not commit passwords or database credentials.

## Important

This is an MVP starter, not a production-audited SaaS.
Test tenant isolation and permissions before using real
customer data. Configure managed database backups,
secure deployment settings and persistent file storage.
WhatsApp links open a pre-filled message; automatic
messaging requires the official WhatsApp Business API.