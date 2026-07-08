from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine

from src.config import postgres_config
from src.db_client import DBClient
from src.review_service import ReviewService
from src.sql_models import create_table


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_engine = create_async_engine(postgres_config.URL)
    await create_table(db_engine)
    db_client = DBClient(db_engine)
    review_service = ReviewService(db_client)
    app.state.review_service = review_service

    yield

    await db_client.stop()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    return app
