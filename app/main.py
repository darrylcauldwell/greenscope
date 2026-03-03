import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from pythonjsonlogger.json import JsonFormatter

from app.config import settings
from app.database import init_db
from app.routers import health, pages, sci
from app.services.scheduler import start_scheduler, stop_scheduler

# JSON structured logging
handler = logging.StreamHandler(sys.stdout)
formatter = JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
    rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
)
handler.setFormatter(formatter)
logging.root.handlers = [handler]
logging.root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting GreenScope")
    await init_db()
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("GreenScope stopped")


app = FastAPI(title="GreenScope", lifespan=lifespan)

# Prometheus HTTP metrics
Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    excluded_handlers=["/health", "/metrics"],
).instrument(app).expose(app, endpoint="/metrics")

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Routers
app.include_router(health.router)
app.include_router(sci.router)
app.include_router(pages.router)
