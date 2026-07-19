from fastapi import FastAPI

from .config import get_settings
from .routers import bookings, listings, messages, reviews, users

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


@app.get("/healthz", tags=["ops"])
def healthz():
    return {"ok": True, "env": get_settings().env}
