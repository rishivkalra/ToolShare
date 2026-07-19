from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routers import bookings, internal, listings, messages, projects, reviews, users

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(
    title="ToolShare API",
    version="0.1.0",
    description="Hyperlocal peer-to-peer tool rental. Neighbors rent idle tools "
    "to each other for a few dollars a day.",
)

app.include_router(users.router)
app.include_router(listings.router)
app.include_router(bookings.router)
app.include_router(messages.router)
app.include_router(reviews.router)
app.include_router(projects.router)
app.include_router(internal.router)


@app.get("/health", tags=["ops"])
def healthz():
    return {"ok": True, "env": get_settings().env}


@app.get("/", include_in_schema=False)
def root():
    """Browser landing: the web app if bundled, else the API docs."""
    return RedirectResponse(url="/app/" if WEB_DIR.exists() else "/docs")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


if WEB_DIR.exists():
    app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")
