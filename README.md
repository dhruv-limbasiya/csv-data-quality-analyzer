# CSV Data Quality Analyzer

A full-stack web application for analyzing and improving the quality of CSV datasets. Upload your data, detect quality issues, apply cleaning operations, and download improved datasets — all through an intuitive browser interface.

## Features

- **User Authentication** — Secure registration and login with HTTP-only cookie sessions
- **CSV Upload & Inspection** — Upload CSV files and inspect their structure, columns, and data types
- **Data Quality Analysis** — Detect missing values, duplicates, type mismatches, inconsistent categories, invalid values, and outliers
- **Quality Scoring** — Receive a weighted composite quality score (0–100) per column and overall
- **Data Cleaning** — Select cleaning operations, preview results before applying, and compare original vs. cleaned data
- **Exports** — Download cleaned CSV files and quality reports
- **Analysis History** — View and revisit all previous analyses and cleaning operations

> The original uploaded dataset is never silently modified.

## Tech Stack

| Layer | Technologies |
|---|---|
| **Frontend** | React, Vite, JavaScript/JSX, Tailwind CSS, React Router, Axios, Recharts, Lucide React |
| **Backend** | Python 3.13, FastAPI, Uvicorn, Pandas, NumPy, SQLAlchemy 2, Alembic, Pydantic |
| **Database** | PostgreSQL 18 |
| **Testing** | pytest, HTTPX |

## Project Structure

```
├── backend/          # FastAPI application
├── frontend/         # React / Vite application
├── sample_data/      # Example CSV files for testing
├── docs/             # Project documentation
├── .gitignore
└── README.md
```

## Getting Started

> Full setup instructions will be added as the project develops.

### Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL 14+
- Git

### Quick Start

```bash
# Clone the repository
git clone <repository-url>
cd "CSV Data Quality Analyzer"

# Backend setup
cd backend
python -m venv venv
venv\Scripts\activate       # Windows
pip install -r requirements.txt
cp .env.example .env        # Edit with your database credentials
alembic upgrade head
uvicorn app.main:app --reload

# Frontend setup (in a new terminal)
cd frontend
npm install
npm run dev
```

## License

This project is part of a portfolio submission.
