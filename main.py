"""FastAPI application, health checks, and the local search interface."""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from web_search import router
from mysql.connector import Error

import db

app = FastAPI(title="MY_CUSTOM_BOT")
app.include_router(router)
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")


@app.get("/")
def welcome() -> dict[str, str]:
    return {"message": "Hello! Welcome to MY_CUSTOM_BOT application, DSE I2400 Project"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/db-health")
def database_health() -> dict[str, str | list[str]]:
    """A successful table query verifies connectivity and database access."""
    try:
        tables = db.get_table_names()
    except (Error, ValueError):
        raise HTTPException(status_code=503, detail="Database unavailable; check local configuration and MySQL.") from None
    return {"status": "ok", "tables": tables}
