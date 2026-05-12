import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import structlog
from anthropic import Anthropic
from sentence_transformers import SentenceTransformer

from app.generation.prompts import BACK_TRANSLATION_SYSTEM

log = structlog.get_logger(__name__)

_MODEL_NAME = "all-MiniLM-L6-v2"
_embedder: SentenceTransformer | None = None


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(_MODEL_NAME)
    return _embedder


@dataclass
class BackTranslationResult:
    original_question: str
    back_translated_question: str
    similarity_score: float
    hallucination_suspected: bool
    confidence_level: str


def back_translate(
    sql: str,
    anthropic_client: Anthropic,
    model: str,
) -> str:
    """Ask the LLM what question the given SQL answers."""
    response = anthropic_client.messages.create(
        model=model,
        max_tokens=300,
        system=BACK_TRANSLATION_SYSTEM,
        messages=[{"role": "user", "content": f"SQL query:\n```sql\n{sql}\n```\n\nWhat question does this SQL answer?"}],
    )
    return response.content[0].text.strip()


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def check_back_translation(
    original_question: str,
    sql: str,
    anthropic_client: Anthropic,
    model: str,
    threshold: float = 0.75,
) -> tuple[BackTranslationResult, float]:
    """
    Run back-translation hallucination detection.
    Returns (BackTranslationResult, latency_ms).
    """
    t0 = time.perf_counter()

    back_q = back_translate(sql, anthropic_client, model)
    embedder = _get_embedder()
    embeddings = embedder.encode([original_question, back_q])
    sim = cosine_similarity(embeddings[0], embeddings[1])

    hallucination_suspected = sim < threshold
    if sim >= 0.85:
        confidence = "HIGH"
    elif sim >= 0.70:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    latency_ms = (time.perf_counter() - t0) * 1000

    result = BackTranslationResult(
        original_question=original_question,
        back_translated_question=back_q,
        similarity_score=round(sim, 4),
        hallucination_suspected=hallucination_suspected,
        confidence_level=confidence,
    )
    log.info(
        "back_translation",
        similarity=round(sim, 4),
        hallucination_suspected=hallucination_suspected,
        confidence=confidence,
        latency_ms=round(latency_ms, 1),
    )
    return result, latency_ms
