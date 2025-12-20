"""
短期记忆层管理器 (Short-term Memory Manager)

负责管理短期记忆：
- 从激活的感知记忆块提取结构化记忆
- LLM 决策：合并、更新、创建、丢弃
- 容量管理和转移到长期记忆
"""

import asyncio
import json
import re
import uuid
from pathlib import Path
from typing import Any

import json_repair
import numpy as np

from src.common.logger import get_logger
from src.memory_graph.models import (
    MemoryBlock,
    ShortTermDecision,
    ShortTermMemory,
    ShortTermOperation,
)
from src.memory_graph.utils.embeddings import EmbeddingGenerator
from src.memory_graph.utils.similarity import cosine_similarity_async

logger = get_logger(__name__)


class ShortTermMemoryManager:
    """
    短期记忆层管理器

    管理活跃的结构化记忆，介于感知记忆和长期记忆之间。
    """

    def __init__(
        self,
        data_dir: Path | None = None,
        max_memories: int = 30,
        transfer_importance_threshold: float = 0.6,
        llm_temperature: float = 0.2,
        enable_force_cleanup: bool = False,
        cleanup_keep_ratio: float = 0.9,
        overflow_strategy: str = "transfer_all",
    ):
        """
        初始化短期记忆层管理器

        Args:
            data_dir: 数据存储目录
            max_memories: 最大短期记忆数量
            transfer_importance_threshold: 转移到长期记忆的重要性阈值
            llm_temperature: LLM 决策的温度参数
            enable_force_cleanup: 是否启用泄压功能
            cleanup_keep_ratio: 泄压时保留容量的比例（默认0.9表示保留90%）
            overflow_strategy: 短期记忆溢出策略
                - "transfer_all": 一次性转移所有记忆到长期记忆，并删除不重要的短期记忆（默认）
                - "selective_cleanup": 选择性清理，仅转移重要记忆，直接删除低重要性记忆
        """
        self.data_dir = data_dir or Path("data/memory_graph")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 配置参数
        self.max_memories = max_memories
        self.transfer_importance_threshold = transfer_importance_threshold
        self.llm_temperature = llm_temperature
        self.enable_force_cleanup = enable_force_cleanup
        self.cleanup_keep_ratio = cleanup_keep_ratio
        self.overflow_strategy = overflow_strategy  # 新增：溢出策略

        # 核心数据
        self.memories: list[ShortTermMemory] = []
        self.embedding_generator: EmbeddingGenerator | None = None

        # 优化：快速查找索引
        self._memory_id_index: dict[str, ShortTermMemory] = {}  # ID 快速查找
        self._similarity_cache: dict[str, dict[str, float]] = {}  # 相似度缓存 {query_id: {target_id: sim}}
        self._emb_matrix: np.ndarray | None = None
        self._emb_matrix_mem_ids: list[str] | None = None

        # 状态
        self._initialized = False
        self._save_lock = asyncio.Lock()

        logger.info(
            f"短期记忆管理器已创建 (max_memories={max_memories}, "
            f"transfer_threshold={transfer_importance_threshold:.2f}, "
            f"overflow_strategy={overflow_strategy}, "
            f"force_cleanup={'on' if enable_force_cleanup else 'off'})"
        )

    async def initialize(self) -> None:
        """初始化管理器"""
        if self._initialized:
            logger.warning("短期记忆管理器已经初始化")
            return

        try:
            logger.debug("开始初始化短期记忆管理器...")

            # 初始化嵌入生成器
            self.embedding_generator = EmbeddingGenerator()

            # 尝试加载现有数据
            await self._load_from_disk()

            self._initialized = True
            logger.debug(f"短期记忆管理器初始化完成 (已加载 {len(self.memories)} 条记忆)")

        except Exception as e:
            logger.error(f"短期记忆管理器初始化失败: {e}")
            raise

    async def add_from_block(self, block: MemoryBlock) -> ShortTermMemory | None:
        """
        从激活的感知记忆块创建短期记忆

        流程：
        1. 使用 LLM 从记忆块提取结构化信息
        2. 与现有短期记忆比较，决定如何处理（MERGE/UPDATE/CREATE_NEW/DISCARD）
        3. 执行决策
        4. 检查是否达到容量上限

        Args:
            block: 已激活的记忆块

        Returns:
            新创建或更新的短期记忆，失败或丢弃返回 None
        """
        if not self._initialized:
            await self.initialize()

        try:
            logger.debug(f"开始处理记忆块: {block.id}")

            # 步骤1: 使用 LLM 提取结构化记忆
            extracted_memory = await self._extract_structured_memory(block)
            if not extracted_memory:
                logger.warning(f"记忆块 {block.id} 提取失败，跳过")
                return None

            # 步骤2: 决策如何处理新记忆
            decision = await self._decide_memory_operation(extracted_memory)
            logger.debug(f"LLM 决策: {decision}")

            # 步骤3: 执行决策
            result_memory = await self._execute_decision(extracted_memory, decision)

            # 步骤4: 检查容量并可能触发转移
            if len(self.memories) >= self.max_memories:
                logger.warning(
                    f"短期记忆已达上限 ({len(self.memories)}/{self.max_memories})，"
                    f"需要转移到长期记忆"
                )
                # 注意：实际转移由外部调用 transfer_to_long_term()

            # 异步保存
            asyncio.create_task(self._save_to_disk())

            return result_memory

        except Exception as e:
            logger.error(f"添加短期记忆失败: {e}")
            return None

    async def _extract_structured_memory(self, block: MemoryBlock) -> ShortTermMemory | None:
        """
        使用 LLM 从记忆块提取结构化信息

        Args:
            block: 记忆块

        Returns:
            提取的短期记忆，失败返回 None
        """
        try:
            from src.config.config import model_config
            from src.llm_models.utils_model import LLMRequest

            # 构建提示词
            prompt = f"""你是一个记忆提取专家。请从以下对话片段中提取一条结构化的记忆。

**对话内容：**
```
{block.combined_text}
```

**任务要求：**
1. 提取对话的核心信息，形成一条简洁的记忆描述
2. 识别记忆的主体（subject）、主题（topic）、客体（object）
3. 判断记忆类型（event/fact/opinion/relation）
4. 评估重要性（0.0-1.0）

**输出格式（JSON）：**
```json
{{
  "content": "记忆的完整描述",
  "subject": "主体",
  "topic": "主题/动作",
  "object": "客体",
  "memory_type": "event/fact/opinion/relation",
  "importance": 0.7,
  "attributes": {{
    "time": "时间信息",
    "attribute1": "其他属性1",
    "attribute2": "其他属性2",
    ...
  }}
}}
```

请输出JSON："""

            # 调用短期记忆构建模型
            llm = LLMRequest(
                model_set=model_config.model_task_config.memory_short_term_builder,
                request_type="short_term_memory.extract",
            )

            response, _ = await llm.generate_response_async(
                prompt,
                temperature=self.llm_temperature,
                max_tokens=800,
            )

            # 解析响应
            data = self._parse_json_response(response)
            if not data:
                logger.error(f"LLM 响应解析失败: {response[:200]}")
                return None

            # 生成向量
            content = data.get("content", "")
            embedding = await self._generate_embedding(content)

            # 创建短期记忆
            memory = ShortTermMemory(
                id=f"stm_{uuid.uuid4().hex[:12]}",
                content=content,
                embedding=embedding,
                importance=data.get("importance", 0.5),
                source_block_ids=[block.id],
                subject=data.get("subject"),
                topic=data.get("topic"),
                object=data.get("object"),
                memory_type=data.get("memory_type"),
                attributes=data.get("attributes", {}),
            )

            logger.debug(f"提取结构化记忆: {memory.content[:50]}...")
            return memory

        except Exception as e:
            logger.error(f"提取结构化记忆失败: {e}")
            return None

    async def _decide_memory_operation(self, new_memory: ShortTermMemory) -> ShortTermDecision:
        """
        使用 LLM 决定如何处理新记忆

        Args:
            new_memory: 新提取的短期记忆

        Returns:
            决策结果
        """
        try:
            from src.config.config import model_config
            from src.llm_models.utils_model import LLMRequest

            # 查找相似的现有记忆
            similar_memories = await self._find_similar_memories(new_memory, top_k=5)

            # 如果没有相似记忆，直接创建新记忆
            if not similar_memories:
                return ShortTermDecision(
                    operation=ShortTermOperation.CREATE_NEW,
                    reasoning="没有找到相似的现有记忆，作为新记忆保存",
                    confidence=1.0,
                )

            # 构建提示词
            existing_memories_desc = "\n\n".join(
                [
                    f"记忆{i+1} (ID: {mem.id}, 重要性: {mem.importance:.2f}, 相似度: {sim:.2f}):\n{mem.content}"
                    for i, (mem, sim) in enumerate(similar_memories)
                ]
            )

            prompt = f"""你是一个记忆管理专家。现在有一条新记忆需要处理，请决定如何操作。

**新记忆：**
{new_memory.content}

**现有相似记忆：**
{existing_memories_desc}

**操作选项：**
1. merge - 合并到现有记忆（内容高度重叠或互补）
2. update - 更新现有记忆（新信息修正或补充旧信息）
3. create_new - 创建新记忆（与现有记忆不同的独立信息）
4. discard - 丢弃（价值过低或完全重复）
5. keep_separate - 暂保持独立（相关但独立的信息）

**输出格式（JSON）：**
```json
{{
  "operation": "merge/update/create_new/discard/keep_separate",
  "target_memory_id": "目标记忆的ID（merge/update时需要）",
  "merged_content": "合并/更新后的完整内容",
  "reasoning": "决策理由",
  "confidence": 0.85,
  "updated_importance": 0.7
}}
```

请输出JSON："""

            # 调用短期记忆决策模型
            llm = LLMRequest(
                model_set=model_config.model_task_config.memory_short_term_decider,
                request_type="short_term_memory.decide",
            )

            response, _ = await llm.generate_response_async(
                prompt,
                temperature=self.llm_temperature,
                max_tokens=1000,
            )

            # 解析响应
            data = self._parse_json_response(response)
            if not data:
                logger.error(f"LLM 决策响应解析失败: {response[:200]}")
                # 默认创建新记忆
                return ShortTermDecision(
                    operation=ShortTermOperation.CREATE_NEW,
                    reasoning="LLM 响应解析失败，默认创建新记忆",
                    confidence=0.5,
                )

            # 创建决策对象
            # 规范化操作名，兼容连字符与大小写差异
            op_raw = data.get("operation", "create_new")
            operation_str = op_raw.strip().lower().replace("-", "_")
            try:
                op_enum = ShortTermOperation(operation_str)
            except Exception:
                op_enum = ShortTermOperation.CREATE_NEW

            decision = ShortTermDecision(
                operation=op_enum,
                target_memory_id=data.get("target_memory_id"),
                merged_content=data.get("merged_content"),
                reasoning=data.get("reasoning", ""),
                confidence=data.get("confidence", 0.5),
                updated_importance=data.get("updated_importance"),
            )

            logger.debug(f"LLM 决策完成: {decision}")
            return decision

        except Exception as e:
            logger.error(f"LLM 决策失败: {e}")
            # 默认创建新记忆
            return ShortTermDecision(
                operation=ShortTermOperation.CREATE_NEW,
                reasoning=f"LLM 决策失败: {e}",
                confidence=0.3,
            )

    async def _execute_decision(
        self, new_memory: ShortTermMemory, decision: ShortTermDecision
    ) -> ShortTermMemory | None:
        """
        执行 LLM 的决策

        Args:
            new_memory: 新记忆
            decision: 决策结果

        Returns:
            最终的记忆对象（可能是新建或更新的），失败或丢弃返回 None
        """
        try:
            if decision.operation == ShortTermOperation.CREATE_NEW:
                # 创建新记忆
                self.memories.append(new_memory)
                self._memory_id_index[new_memory.id] = new_memory  # 更新索引
                self._invalidate_matrix_cache()
                logger.debug(f"创建新短期记忆: {new_memory.id}")
                return new_memory

            elif decision.operation == ShortTermOperation.MERGE:
                # 合并到现有记忆
                target = self._find_memory_by_id(decision.target_memory_id)
                if not target:
                    logger.warning(f"目标记忆不存在，改为创建新记忆: {decision.target_memory_id}")
                    self.memories.append(new_memory)
                    self._memory_id_index[new_memory.id] = new_memory
                    self._invalidate_matrix_cache()
                    return new_memory

                # 更新内容
                target.content = decision.merged_content or f"{target.content}\n{new_memory.content}"
                target.source_block_ids.extend(new_memory.source_block_ids)

                # 更新重要性
                if decision.updated_importance is not None:
                    target.importance = decision.updated_importance

                # 重新生成向量
                target.embedding = await self._generate_embedding(target.content)
                target.update_access()

                # 清除此记忆的缓存
                self._similarity_cache.pop(target.id, None)
                self._invalidate_matrix_cache()

                logger.debug(f"合并记忆到: {target.id}")
                return target

            elif decision.operation == ShortTermOperation.UPDATE:
                # 更新现有记忆
                target = self._find_memory_by_id(decision.target_memory_id)
                if not target:
                    logger.warning(f"目标记忆不存在，改为创建新记忆: {decision.target_memory_id}")
                    self.memories.append(new_memory)
                    self._memory_id_index[new_memory.id] = new_memory
                    self._invalidate_matrix_cache()
                    return new_memory

                # 更新内容
                if decision.merged_content:
                    target.content = decision.merged_content
                    target.embedding = await self._generate_embedding(target.content)

                # 更新重要性
                if decision.updated_importance is not None:
                    target.importance = decision.updated_importance

                target.source_block_ids.extend(new_memory.source_block_ids)
                target.update_access()

                # 清除此记忆的缓存
                self._similarity_cache.pop(target.id, None)
                self._invalidate_matrix_cache()

                logger.debug(f"更新记忆: {target.id}")
                return target

            elif decision.operation == ShortTermOperation.DISCARD:
                # 丢弃
                logger.debug(f"丢弃低价值记忆: {decision.reasoning}")
                return None

            elif decision.operation == ShortTermOperation.KEEP_SEPARATE:
                # 保持独立
                self.memories.append(new_memory)
                self._memory_id_index[new_memory.id] = new_memory  # 更新索引
                self._invalidate_matrix_cache()
                logger.debug(f"保持独立记忆: {new_memory.id}")
                return new_memory

            else:
                logger.warning(f"未知操作类型: {decision.operation}，默认创建新记忆")
                self.memories.append(new_memory)
                self._memory_id_index[new_memory.id] = new_memory
                self._invalidate_matrix_cache()
                return new_memory

        except Exception as e:
            logger.error(f"执行决策失败: {e}")
            return None

    async def _find_similar_memories(
        self, memory: ShortTermMemory, top_k: int = 5
    ) -> list[tuple[ShortTermMemory, float]]:
        """
        查找与给定记忆相似的现有记忆（优化版：并发计算 + 缓存）

        Args:
            memory: 目标记忆
            top_k: 返回的最大数量

        Returns:
            (记忆, 相似度) 列表，按相似度降序
        """
        if memory.embedding is None or len(memory.embedding) == 0 or not self.memories:
            return []

        try:
            # 检查缓存
            if memory.id in self._similarity_cache:
                cached = self._similarity_cache[memory.id]
                scored = [(self._memory_id_index[mid], sim)
                         for mid, sim in cached.items()
                         if mid in self._memory_id_index]
                scored.sort(key=lambda x: x[1], reverse=True)
                return scored[:top_k]

            valid_memories, matrix = await self._ensure_embeddings_matrix()
            if not valid_memories or matrix is None:
                return []

            q = memory.embedding.astype(np.float32)
            sims = await self._compute_cosine_similarities_vectorized(q, matrix)
            if sims is None or len(sims) == 0:
                return []

            # 构建结果并缓存
            scored = []
            cache_entry = {}
            for existing_mem, similarity in zip(valid_memories, sims):
                scored.append((existing_mem, float(similarity)))
                cache_entry[existing_mem.id] = float(similarity)

            self._similarity_cache[memory.id] = cache_entry

            # 按相似度降序排序
            scored.sort(key=lambda x: x[1], reverse=True)

            return scored[:top_k]

        except Exception as e:
            logger.error(f"查找相似记忆失败: {e}")
            return []

    def _find_memory_by_id(self, memory_id: str | None) -> ShortTermMemory | None:
        """根据ID查找记忆（优化版：O(1) 哈希表查找）"""
        if not memory_id:
            return None

        # 使用索引进行 O(1) 查找
        return self._memory_id_index.get(memory_id)

    async def _generate_embedding(self, text: str) -> np.ndarray | None:
        """生成文本向量"""
        try:
            if not self.embedding_generator:
                logger.error("嵌入生成器未初始化")
                return None

            embedding = await self.embedding_generator.generate(text)
            return self._normalize_embedding(embedding)

        except Exception as e:
            logger.error(f"生成向量失败: {e}")
            return None

    async def _generate_embeddings_batch(self, texts: list[str]) -> list[np.ndarray | None]:
        """
        批量生成文本向量

        Args:
            texts: 文本列表

        Returns:
            向量列表，与输入一一对应
        """
        try:
            if not self.embedding_generator:
                logger.error("嵌入生成器未初始化")
                return [None] * len(texts)

            embeddings = await self.embedding_generator.generate_batch(texts)
            return [self._normalize_embedding(e) for e in embeddings]

        except Exception as e:
            logger.error(f"批量生成向量失败: {e}")
            return [None] * len(texts)

    def _parse_json_response(self, response: str) -> dict[str, Any] | None:
        """解析 LLM 的 JSON 响应"""
        try:
            # 尝试提取 JSON 代码块
            json_match = re.search(r"```json\s*(.*?)\s*```", response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 兼容未标注语言的代码块
                any_block = re.search(r"```\s*(.*?)\s*```", response, re.DOTALL)
                if any_block:
                    json_str = any_block.group(1)
                else:
                    # 尝试直接解析原文
                    json_str = response.strip()

            # 移除可能的注释
            json_str = re.sub(r"//.*", "", json_str)
            json_str = re.sub(r"/\*.*?\*/", "", json_str, flags=re.DOTALL)

            try:
                data = json_repair.loads(json_str)
            except Exception:
                # 回退：提取第一个花括号包围的 JSON 片段
                start = json_str.find("{")
                end = json_str.rfind("}")
                if start != -1 and end != -1 and end > start:
                    data = json_repair.loads(json_str[start : end + 1])
                else:
                    raise
            return data

        except Exception as e:
            logger.warning(f"JSON 解析失败: {e}, 响应: {response[:200]}")
            return None

    async def search_memories(
        self, query_text: str, top_k: int = 5, similarity_threshold: float = 0.5
    ) -> list[ShortTermMemory]:
        """
        检索相关的短期记忆（优化版：并发计算相似度）

        Args:
            query_text: 查询文本
            top_k: 返回的最大数量
            similarity_threshold: 相似度阈值

        Returns:
            检索到的记忆列表
        """
        if not self._initialized:
            await self.initialize()

        try:
            # 生成查询向量
            query_embedding = await self._generate_embedding(query_text)
            if query_embedding is None or len(query_embedding) == 0:
                return []

            valid_memories, matrix = await self._ensure_embeddings_matrix()
            if not valid_memories or matrix is None:
                return []

            q = query_embedding.astype(np.float32)
            sims = await self._compute_cosine_similarities_vectorized(q, matrix)

            # 构建结果
            scored = []
            for memory, similarity in zip(valid_memories, sims):
                if float(similarity) >= similarity_threshold:
                    scored.append((memory, float(similarity)))

            # 排序并取 TopK
            scored.sort(key=lambda x: x[1], reverse=True)
            results = [mem for mem, _ in scored[:top_k]]

            # 批量更新访问记录
            for mem in results:
                mem.update_access()

            logger.debug(f"检索到 {len(results)} 条短期记忆")
            return results

        except Exception as e:
            logger.error(f"检索短期记忆失败: {e}")
            return []

    def get_memories_for_transfer(self) -> list[ShortTermMemory]:
        """
        获取需要转移到长期记忆的记忆（简化版：满额整批转移）

        策略：
        - 当短期记忆数量达到上限（>= max_memories）时，返回当前全部短期记忆；
        - 没满则返回空列表，不触发转移。
        """
        if self.max_memories <= 0:
            return []
        if len(self.memories) >= self.max_memories:
            logger.debug(f"转移候选: 短期记忆已满，准备整批转移 {len(self.memories)} 条")
            return list(self.memories)
        return []

    def force_cleanup_overflow(self, keep_ratio: float | None = None) -> int:
        """
        当短期记忆超过容量时，强制删除低重要性且最早的记忆以泄压
        
        Args:
            keep_ratio: 保留容量的比例（默认使用配置中的 cleanup_keep_ratio）
        
        Returns:
            删除的记忆数量
        """
        if not self.enable_force_cleanup:
            return 0

        if self.max_memories <= 0:
            return 0

        # 使用实例配置或传入参数
        if keep_ratio is None:
            keep_ratio = self.cleanup_keep_ratio

        current = len(self.memories)
        limit = int(self.max_memories * keep_ratio)
        if current <= self.max_memories:
            return 0

        # 先按重要性升序，再按创建时间升序删除
        sorted_memories = sorted(self.memories, key=lambda m: (m.importance, m.created_at))
        remove_count = max(0, current - limit)
        to_remove = {mem.id for mem in sorted_memories[:remove_count]}

        if not to_remove:
            return 0

        self.memories = [mem for mem in self.memories if mem.id not in to_remove]
        for mem_id in to_remove:
            self._memory_id_index.pop(mem_id, None)
            self._similarity_cache.pop(mem_id, None)
        self._invalidate_matrix_cache()

        # 异步保存即可，不阻塞主流程
        asyncio.create_task(self._save_to_disk())

        logger.warning(
            f"短期记忆压力泄压: 移除 {len(to_remove)} 条 (当前 {len(self.memories)}/{self.max_memories})"
        )

        return len(to_remove)

    async def clear_transferred_memories(self, memory_ids: list[str]) -> None:
        """
        清除已转移到长期记忆的记忆
        
        在 "transfer_all" 策略下，还会删除不重要的短期记忆以释放空间

        Args:
            memory_ids: 已转移的记忆ID列表
        """
        try:
            remove_ids = set(memory_ids)
            self.memories = [mem for mem in self.memories if mem.id not in remove_ids]

            # 更新索引
            for mem_id in remove_ids:
                self._memory_id_index.pop(mem_id, None)
                self._similarity_cache.pop(mem_id, None)

            logger.info(f"清除 {len(memory_ids)} 条已转移的短期记忆")

            # 在 "transfer_all" 策略下，进一步删除不重要的短期记忆
            if self.overflow_strategy == "transfer_all":
                # 计算需要删除的低重要性记忆数量
                low_importance_memories = [
                    mem for mem in self.memories
                    if mem.importance < self.transfer_importance_threshold
                ]

                if low_importance_memories:
                    # 按重要性和创建时间排序，删除最不重要的
                    low_importance_memories.sort(key=lambda m: (m.importance, m.created_at))

                    # 删除所有低重要性记忆
                    to_delete = {mem.id for mem in low_importance_memories}
                    self.memories = [mem for mem in self.memories if mem.id not in to_delete]

                    # 更新索引
                    for mem_id in to_delete:
                        self._memory_id_index.pop(mem_id, None)
                        self._similarity_cache.pop(mem_id, None)

                    logger.info(
                        f"transfer_all 策略: 额外删除了 {len(to_delete)} 条低重要性记忆 "
                        f"(重要性 < {self.transfer_importance_threshold:.2f})"
                    )

            # 异步保存
            asyncio.create_task(self._save_to_disk())
            self._invalidate_matrix_cache()

        except Exception as e:
            logger.error(f"清除已转移记忆失败: {e}")

    def get_statistics(self) -> dict[str, Any]:
        """获取短期记忆层统计信息"""
        if not self._initialized:
            return {}

        total_access = sum(mem.access_count for mem in self.memories)
        avg_importance = sum(mem.importance for mem in self.memories) / len(self.memories) if self.memories else 0

        return {
            "total_memories": len(self.memories),
            "max_memories": self.max_memories,
            "total_access_count": total_access,
            "avg_importance": avg_importance,
            "transferable_count": len(self.get_memories_for_transfer()),
            "transfer_threshold": self.transfer_importance_threshold,
        }

    async def _save_to_disk(self) -> None:
        """保存短期记忆到磁盘"""
        async with self._save_lock:
            try:
                import orjson

                save_path = self.data_dir / "short_term_memory.json"
                data = {
                    "memories": [mem.to_dict() for mem in self.memories],
                    "max_memories": self.max_memories,
                    "transfer_threshold": self.transfer_importance_threshold,
                }

                save_path.write_bytes(orjson.dumps(data, option=orjson.OPT_INDENT_2))

                logger.debug(f"短期记忆已保存到 {save_path}")

            except Exception as e:
                logger.error(f"保存短期记忆失败: {e}")

    async def _load_from_disk(self) -> None:
        """从磁盘加载短期记忆"""
        try:
            import orjson

            load_path = self.data_dir / "short_term_memory.json"

            if not load_path.exists():
                logger.info("未找到短期记忆数据文件")
                return

            data = orjson.loads(load_path.read_bytes())
            self.memories = [ShortTermMemory.from_dict(m) for m in data.get("memories", [])]

            # 重建索引
            for mem in self.memories:
                self._memory_id_index[mem.id] = mem

            # 批量重新生成向量
            await self._reload_embeddings()

            self._invalidate_matrix_cache()

            logger.info(f"短期记忆已从 {load_path} 加载 ({len(self.memories)} 条)")

        except Exception as e:
            logger.error(f"加载短期记忆失败: {e}")

    async def _reload_embeddings(self) -> None:
        """重新生成记忆的向量（优化版：并发处理）"""
        logger.info("重新生成短期记忆向量...")

        memories_to_process = []
        texts_to_process = []

        for memory in self.memories:
            if memory.embedding is None and memory.content and memory.content.strip():
                memories_to_process.append(memory)
                texts_to_process.append(memory.content)

        if not memories_to_process:
            logger.info("没有需要重新生成向量的短期记忆")
            return

        logger.info(f"开始批量生成 {len(memories_to_process)} 条短期记忆的向量...")

        # 使用 gather 并发生成向量
        embeddings = await self._generate_embeddings_batch(texts_to_process)

        success_count = 0
        for memory, embedding in zip(memories_to_process, embeddings):
            if embedding is not None:
                memory.embedding = embedding
                success_count += 1

        logger.info(f"向量重新生成完成（成功: {success_count}/{len(memories_to_process)}）")
        self._invalidate_matrix_cache()

    def _normalize_embedding(self, emb: np.ndarray | None) -> np.ndarray | None:
        if emb is None:
            return None
        v = emb.astype(np.float32)
        n = float(np.linalg.norm(v))
        if n == 0.0:
            return v
        return v / n

    def _invalidate_matrix_cache(self) -> None:
        self._emb_matrix = None
        self._emb_matrix_mem_ids = None
        self._similarity_cache.clear()

    async def _ensure_embeddings_matrix(self) -> tuple[list[ShortTermMemory], np.ndarray | None]:
        if self._emb_matrix is not None and self._emb_matrix_mem_ids is not None:
            mems = [self._memory_id_index[mid] for mid in self._emb_matrix_mem_ids if mid in self._memory_id_index]
            return mems, self._emb_matrix

        valid_memories = [m for m in self.memories if m.embedding is not None]
        if not valid_memories:
            self._emb_matrix = None
            self._emb_matrix_mem_ids = None
            return [], None

        matrix = np.array([m.embedding for m in valid_memories], dtype=np.float32)
        self._emb_matrix = matrix
        self._emb_matrix_mem_ids = [m.id for m in valid_memories]
        return valid_memories, matrix

    async def _compute_cosine_similarities_vectorized(
        self, query_embedding: np.ndarray, matrix: np.ndarray
    ) -> np.ndarray | None:
        try:
            if query_embedding is None or len(query_embedding) == 0 or matrix is None or matrix.ndim != 2:
                return None
            return await asyncio.to_thread(self._compute_cosine_similarities_np, query_embedding, matrix)
        except Exception as e:
            logger.error(f"向量化相似度计算失败: {e}")
            return None

    def _compute_cosine_similarities_np(self, q: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        return matrix @ q

    async def shutdown(self) -> None:
        """关闭管理器"""
        if not self._initialized:
            return

        try:
            logger.info("正在关闭短期记忆管理器...")

            # 最后一次保存
            await self._save_to_disk()

            self._initialized = False
            logger.info("短期记忆管理器已关闭")

        except Exception as e:
            logger.error(f"关闭短期记忆管理器失败: {e}")


# 全局单例
_short_term_manager_instance: ShortTermMemoryManager | None = None


def get_short_term_manager() -> ShortTermMemoryManager:
    """获取短期记忆管理器单例"""
    global _short_term_manager_instance
    if _short_term_manager_instance is None:
        _short_term_manager_instance = ShortTermMemoryManager()
    return _short_term_manager_instance
