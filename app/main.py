from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import engine
from app.core.exception_handlers import register_exception_handlers
from app.routers import picks, parlays, dashboard, pipeline, config, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="BetSync API",
        description="Sports betting picks tracker & prediction pipeline",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health.router, tags=["health"])
    app.include_router(picks.router, prefix="/api/v1", tags=["picks"])
    app.include_router(parlays.router, prefix="/api/v1", tags=["parlays"])
    app.include_router(dashboard.router, prefix="/api/v1", tags=["dashboard"])
    app.include_router(pipeline.router, prefix="/api/v1", tags=["pipeline"])
    app.include_router(config.router, prefix="/api/v1", tags=["config"])

    return app


app = create_app()
