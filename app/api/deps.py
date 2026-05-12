from functools import lru_cache
from typing import Any

from anthropic import Anthropic
from sqlalchemy import Engine, create_engine

from app.config import AppConfig, get_config as _get_config
from app.schema.introspection import TableSchema, get_full_schema


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return _get_config()


@lru_cache(maxsize=1)
def get_db_engine() -> Engine:
    config = get_config()
    return create_engine(config.database_url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_anthropic_client() -> Anthropic:
    config = get_config()
    return Anthropic(api_key=config.anthropic_api_key)


@lru_cache(maxsize=1)
def get_full_schema_cached() -> dict[str, TableSchema]:
    engine = get_db_engine()
    return get_full_schema(engine)
