from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routers import (
    auth,
    bookings,
    internal,
    listings,
    messages,
    neighborhoods,
    notifications,
    projects,
    public,
    reports,
    reviews,
    searches,
    users,
    webhooks,
)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(
    title="ToolShare API",
    version="0.1.0",
    description="Hyperlocal peer-to-peer tool rental. Neighbors rent idle tools "
    "to each other for a few dollars a day.",
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(listings.router)
app.include_router(bookings.router)
app.include_router(messages.router)
app.include_router(reviews.router)
app.include_router(projects.router)
app.include_router(internal.router)
app.include_router(reports.router)
app.include_router(notifications.router)
app.include_router(webhooks.router)
app.include_router(neighborhoods.router)
app.include_router(searches.router)
app.include_router(public.router)
app.include_router(listings.photos_router)


@app.get("/health", tags=["ops"])
def healthz():
    return {"ok": True, "env": get_settings().env}


@app.get("/", include_in_schema=False)
def root():
    """Consumer landing page; falls back to the app, then the API docs."""
    landing = WEB_DIR / "landing.html"
    if landing.exists():
        return FileResponse(landing)
    return RedirectResponse(url="/app/" if WEB_DIR.exists() else "/docs")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


if WEB_DIR.exists():
    app.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")
