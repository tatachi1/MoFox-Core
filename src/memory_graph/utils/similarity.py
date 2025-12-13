"""
相似度计算工具

提供统一的向量相似度计算函数
"""

import asyncio
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np


def _compute_similarities_sync(
    query_embedding: "np.ndarray",
    block_embeddings: "np.ndarray | list[np.ndarray] | list[Any]",
    block_norms: "np.ndarray | list[float] | None" = None,
) -> "np.ndarray":
    """
    计算 query 向量与一组向量的余弦相似度（同步/向量化实现）。

    - 返回 float32 ndarray
    - 输出范围裁剪到 [0.0, 1.0]
    - 支持可选的 block_norms 以减少重复 norm 计算
    """
    import numpy as np

    if block_embeddings is None:
        return np.zeros(0, dtype=np.float32)

    query = np.asarray(query_embedding, dtype=np.float32)

    if isinstance(block_embeddings, (list, tuple)) and len(block_embeddings) == 0:
        return np.zeros(0, dtype=np.float32)

    blocks = np.asarray(block_embeddings, dtype=np.float32)
    if blocks.dtype == object:
        blocks = np.stack(
            [np.asarray(vec, dtype=np.float32) for vec in block_embeddings],
            axis=0,
        )

    if blocks.size == 0:
        return np.zeros(0, dtype=np.float32)

    if blocks.ndim == 1:
        blocks = blocks.reshape(1, -1)

    query_norm = float(np.linalg.norm(query))
    if query_norm == 0.0:
        return np.zeros(blocks.shape[0], dtype=np.float32)

    if block_norms is None:
        block_norms_array = np.linalg.norm(blocks, axis=1).astype(np.float32, copy=False)
    else:
        block_norms_array = np.asarray(block_norms, dtype=np.float32)
        if block_norms_array.shape[0] != blocks.shape[0]:
            block_norms_array = np.linalg.norm(blocks, axis=1).astype(np.float32, copy=False)

    dot_products = blocks @ query
    denom = block_norms_array * np.float32(query_norm)

    similarities = np.zeros(blocks.shape[0], dtype=np.float32)
    valid_mask = denom > 0
    if valid_mask.any():
        np.divide(dot_products, denom, out=similarities, where=valid_mask)

    return np.clip(similarities, 0.0, 1.0)


def cosine_similarity(vec1: "np.ndarray", vec2: "np.ndarray") -> float:
    """
    计算两个向量的余弦相似度

    Args:
        vec1: 第一个向量
        vec2: 第二个向量

    Returns:
        余弦相似度 (0.0-1.0)
    """
    try:
        import numpy as np

        vec1 = np.asarray(vec1, dtype=np.float32)
        vec2 = np.asarray(vec2, dtype=np.float32)

        vec1_norm = float(np.linalg.norm(vec1))
        vec2_norm = float(np.linalg.norm(vec2))

        if vec1_norm == 0.0 or vec2_norm == 0.0:
            return 0.0

        similarity = float(np.dot(vec1, vec2) / (vec1_norm * vec2_norm))
        return float(np.clip(similarity, 0.0, 1.0))

    except Exception:
        return 0.0


async def cosine_similarity_async(vec1: "np.ndarray", vec2: "np.ndarray") -> float:
    """
    异步计算两个向量的余弦相似度，使用to_thread避免阻塞

    Args:
        vec1: 第一个向量
        vec2: 第二个向量

    Returns:
        余弦相似度 (0.0-1.0)
    """
    return await asyncio.to_thread(cosine_similarity, vec1, vec2)


def batch_cosine_similarity(vec1: "np.ndarray", vec_list: list["np.ndarray"]) -> list[float]:
    """
    批量计算向量相似度

    Args:
        vec1: 基础向量
        vec_list: 待比较的向量列表

    Returns:
        相似度列表
    """
    try:
        if not vec_list:
            return []

        return _compute_similarities_sync(vec1, vec_list).tolist()

    except Exception:
        return [0.0] * len(vec_list)


async def batch_cosine_similarity_async(vec1: "np.ndarray", vec_list: list["np.ndarray"]) -> list[float]:
    """
    异步批量计算向量相似度，使用to_thread避免阻塞

    Args:
        vec1: 基础向量
        vec_list: 待比较的向量列表

    Returns:
        相似度列表
    """
    return await asyncio.to_thread(batch_cosine_similarity, vec1, vec_list)


__all__ = [
    "batch_cosine_similarity",
    "batch_cosine_similarity_async",
    "cosine_similarity",
    "cosine_similarity_async",
]
