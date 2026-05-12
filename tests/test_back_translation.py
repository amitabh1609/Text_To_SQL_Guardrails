import pytest
from unittest.mock import MagicMock, patch
from app.validation.back_translation import cosine_similarity, BackTranslationResult
import numpy as np


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = np.array([1.0, 2.0, 3.0])
        assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)

    def test_zero_vector(self):
        a = np.array([0.0, 0.0])
        b = np.array([1.0, 2.0])
        assert cosine_similarity(a, b) == 0.0

    def test_similar_vectors(self):
        a = np.array([1.0, 0.9, 0.8])
        b = np.array([1.0, 0.85, 0.75])
        sim = cosine_similarity(a, b)
        assert sim > 0.99


class TestBackTranslationResult:
    def test_hallucination_suspected_below_threshold(self):
        result = BackTranslationResult(
            original_question="How many active suppliers?",
            back_translated_question="This returns total orders",
            similarity_score=0.45,
            hallucination_suspected=True,
            confidence_level="LOW",
        )
        assert result.hallucination_suspected is True
        assert result.confidence_level == "LOW"

    def test_no_hallucination_above_threshold(self):
        result = BackTranslationResult(
            original_question="How many active suppliers?",
            back_translated_question="Count of active suppliers in the database",
            similarity_score=0.91,
            hallucination_suspected=False,
            confidence_level="HIGH",
        )
        assert result.hallucination_suspected is False
        assert result.confidence_level == "HIGH"


class TestCheckBackTranslation:
    def test_integration_with_mock_client(self):
        """Verify the pipeline works end-to-end with a mocked Anthropic client."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Count of active suppliers")]
        mock_client.messages.create.return_value = mock_response

        with patch("app.validation.back_translation._get_embedder") as mock_embedder:
            mock_model = MagicMock()
            # Return high-similarity embeddings
            mock_model.encode.return_value = np.array([
                [1.0, 0.0, 0.0],
                [0.99, 0.1, 0.0],
            ])
            mock_embedder.return_value = mock_model

            from app.validation.back_translation import check_back_translation
            result, latency = check_back_translation(
                "How many active suppliers?",
                "SELECT COUNT(*) FROM suppliers WHERE is_active = TRUE",
                mock_client,
                "claude-sonnet-4-20250514",
                threshold=0.75,
            )

        assert isinstance(result, BackTranslationResult)
        assert latency > 0
        assert result.similarity_score >= 0.0
