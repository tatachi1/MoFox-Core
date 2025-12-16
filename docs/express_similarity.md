# 表达相似度计算策略

本文档说明 `calculate_similarity` 的实现与配置，帮助在质量与性能间做权衡。

## 总览
- 支持两种路径：
  1) **向量化路径（默认优先）**：TF-IDF + 余弦相似度（依赖 `scikit-learn`）
  2) **回退路径**：`difflib.SequenceMatcher`
- 参数 `prefer_vector` 控制是否优先尝试向量化，默认 `True`。
- 依赖缺失或文本过短时，自动回退，无需额外配置。

## 调用方式
```python
from src.chat.express.express_utils import calculate_similarity

sim = calculate_similarity(text1, text2)  # 默认优先向量化
sim_fast = calculate_similarity(text1, text2, prefer_vector=False)  # 强制使用 SequenceMatcher
```

## 依赖与回退
- 可选依赖：`scikit-learn`
  - 缺失时自动回退到 `SequenceMatcher`，不会抛异常。
- 文本过短（长度 < 2）时直接回退，避免稀疏向量噪声。

## 适用建议
- 文本较长、对鲁棒性/语义相似度有更高要求：保持默认（向量化优先）。
- 环境无 `scikit-learn` 或追求极简依赖：调用时设置 `prefer_vector=False`。
- 高并发性能敏感：可在调用点酌情关闭向量化或加缓存。

## 返回范围
- 相似度范围始终在 `[0, 1]`。
- 空字符串 → `0.0`；完全相同 → `1.0`。

## 额外建议
- 若需更强语义能力，可替换为向量数据库或句向量模型（需新增依赖与配置）。
- 对热路径可增加缓存（按文本哈希），或限制输入长度以控制向量维度与内存。
