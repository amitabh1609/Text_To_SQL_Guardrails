import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.query import router

log = structlog.get_logger(__name__)

app = FastAPI(
    title="Text-to-SQL with Guardrails",
    description=(
        "A production-grade natural language interface to a PostgreSQL supply chain database. "
        "Features: SQL guardrails (DDL/DML blocking, injection prevention), "
        "hallucination detection via back-translation, multi-query validation, "
        "and a 50-question golden eval suite."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.on_event("startup")
async def startup():
    log.info("api_startup", version="1.0.0")
