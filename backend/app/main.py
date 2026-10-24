from fastapi import FastAPI, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.config import settings
from app.database import get_db, engine, Base
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("csv_analyzer")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend API for CSV Data Quality Analyzer application"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Root"])
def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API",
        "version": settings.VERSION,
        "docs_url": "/docs"
    }


@app.get("/api/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint that verifies API status and database connectivity."""
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning(f"Database health check failed: {exc}")
        db_status = f"unhealthy: {str(exc)}"

    return {
        "status": "ok" if db_status == "healthy" else "degraded",
        "app": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "database": db_status
    }
