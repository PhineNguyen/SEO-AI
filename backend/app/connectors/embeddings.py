"""Pluggable embedding providers for Hybrid Keyword Clustering (TASK-019)."""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

from app.config import Settings


class BaseEmbeddingProvider(ABC):
    """Unified interface for text embedding providers."""

    provider_name: str = "base"

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return L2-normalized embedding vectors for each input text."""


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI Embeddings API provider (default: text-embedding-3-small)."""

    provider_name = "openai"

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self._api_key = api_key
        self._model = model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key)
        response = client.embeddings.create(model=self._model, input=texts)
        ordered = sorted(response.data, key=lambda item: item.index)
        return [_l2_normalize(list(item.embedding)) for item in ordered]


class SentenceTransformerEmbeddingProvider(BaseEmbeddingProvider):
    """Local multilingual Sentence Transformers embedding provider."""

    provider_name = "sentence_transformers"

    def __init__(self, model_name: str = "intfloat/multilingual-e5-small") -> None:
        self._model_name = model_name
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is not installed. Install backend/requirements-ml.txt."
                ) from exc
            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        vectors = model.encode(texts, normalize_embeddings=True)
        return [list(map(float, row)) for row in vectors]


class DeterministicHashEmbeddingProvider(BaseEmbeddingProvider):
    """Offline deterministic word + character n-gram embedding provider for tests & fallback."""

    provider_name = "deterministic_hash"

    def __init__(self, dims: int = 128) -> None:
        self._dims = dims

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dims
        cleaned = re.sub(r"\s+", " ", text.lower().strip())
        tokens = re.findall(r"[\w]+", cleaned)
        features: list[tuple[str, float]] = []
        for token in tokens:
            features.append((f"w:{token}", 2.0))
            if len(token) >= 3:
                for idx in range(len(token) - 2):
                    features.append((f"c3:{token[idx : idx + 3]}", 0.5))
        for i in range(len(tokens) - 1):
            features.append((f"bi:{tokens[i]}_{tokens[i + 1]}", 1.5))

        for feat, weight in features:
            digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=4).digest()
            bucket = int.from_bytes(digest, "big") % self._dims
            sign = 1.0 if (digest[0] & 1) == 0 else -1.0
            vec[bucket] += sign * weight
        return _l2_normalize(vec)


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


def create_embedding_provider(settings: Settings) -> BaseEmbeddingProvider:
    """Create the configured embedding provider, falling back to deterministic hash if unconfigured."""
    if settings.EMBEDDING_PROVIDER == "sentence_transformers":
        return SentenceTransformerEmbeddingProvider(settings.LOCAL_EMBEDDING_MODEL)
    if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.get_secret_value().strip():
        return OpenAIEmbeddingProvider(
            api_key=settings.OPENAI_API_KEY.get_secret_value().strip(),
            model=settings.OPENAI_EMBEDDING_MODEL,
        )
    return DeterministicHashEmbeddingProvider()
