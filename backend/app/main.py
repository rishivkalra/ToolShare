from fastapi import FastAPI, Response
from fastapi.responses import RedirectResponse

from .config import get_settings
from .routers import bookings, internal, listings, messages, projects, reviews, users

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
    """Browser-friendly landing: send visitors to the interactive API docs."""
    return RedirectResponse(url="/docs")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)
