import hashlib
import math
import re
from typing import Protocol

from .rag_models import EmbeddingProfile


class EmbeddingFailure(Exception):
    pass


def validate_vectors(raw: object, count: int) -> list[list[float]]:
    if not isinstance(raw, list) or len(raw) != count or count == 0:
        raise EmbeddingFailure("Embedding count mismatch")
    vectors: list[list[float]] = []
    dimension = None
    for vector in raw:
        if not isinstance(vector, list) or not 1 <= len(vector) <= 4096:
            raise EmbeddingFailure("Invalid embedding dimension")
        if dimension is None:
            dimension = len(vector)
        if len(vector) != dimension:
            raise EmbeddingFailure("Embedding dimensions differ")
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in vector):
            raise EmbeddingFailure("Invalid embedding number")
        if sum(float(value) ** 2 for value in vector) <= 0:
            raise EmbeddingFailure("Zero embedding")
        vectors.append([float(value) for value in vector])
    return vectors


class Embedder(Protocol):
    model: str
    version: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def profile_for(embedder: Embedder, vectors: list[list[float]]) -> EmbeddingProfile:
    validated = validate_vectors(vectors, len(vectors))
    return EmbeddingProfile(
        model=embedder.model, version=embedder.version, dimension=len(validated[0])
    )


class FixtureEmbedder:
    """Hashed lexical vectors for deterministic wiring tests; not a semantic model."""

    model = "fixture/lexical-128"
    version = "1"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        result = []
        for text in texts:
            vector = [0.0] * 128
            latin = re.findall(r"[a-z0-9]+", text.lower())
            runs = re.findall(r"[\u3400-\u9fff]+", text)
            tokens = latin + [run[i : i + 2] for run in runs for i in range(len(run) - 1)]
            for token in tokens or [text]:
                index = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4]) % 128
                vector[index] += 1
            length = math.sqrt(sum(value * value for value in vector))
            result.append([value / length for value in vector])
        return validate_vectors(result, len(texts))
