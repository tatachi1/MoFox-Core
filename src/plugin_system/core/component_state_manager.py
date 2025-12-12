"""
组件状态管理器模块。

该模块负责管理组件的全局启用/禁用状态以及会话级别的局部（临时）状态。
将状态管理逻辑从 ComponentRegistry 分离出来，实现职责分离。

主要功能:
    - 全局启用/禁用组件
    - 会话级别的局部状态管理
    - 组件可用性检查（综合全局和局部状态）
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.common.logger import get_logger
from src.plugin_system.base.component_types import (
    ComponentInfo,
    ComponentType,
)

if TYPE_CHECKING:
    from src.plugin_system.core.component_registry import ComponentRegistry

logger = get_logger("component_state_manager")


class ComponentStateManager:
    """
    组件状态管理器。

    该类负责管理所有组件的启用/禁用状态，包括:
        - 全局状态: 影响所有会话的组件启用状态
        - 局部状态: 仅影响特定会话（stream_id）的临时状态覆盖

    Attributes:
        _registry: 组件注册中心的引用
        _local_component_states: 局部组件状态管理器
        _no_local_state_types: 不支持局部状态管理的组件类型集合
    """

    def __init__(self, registry: ComponentRegistry):
        """
        初始化组件状态管理器。

        Args:
            registry: 组件注册中心实例的引用
        """
        self._registry = registry

        # 局部组件状态管理器
        # 结构: {stream_id: {(component_name, component_type): enabled}}
        self._local_component_states: dict[str, dict[tuple[str, ComponentType], bool]] = {}

        # 定义不支持局部状态管理的组件类型集合
        # 这些组件类型需要保持全局一致性
        self._no_local_state_types: set[ComponentType] = {
            ComponentType.ROUTER,  # 路由组件需要全局一致性
            ComponentType.EVENT_HANDLER,  # 事件处理器需要全局一致性
            ComponentType.PROMPT,  # 提示词组件需要全局一致性
            ComponentType.ADAPTER, # ADAPTER组件需要全局一致性
        }

        logger.debug("组件状态管理器初始化完成")

    # =================================================================
    # == 全局状态管理 (Global State Management)
    # =================================================================

    def enable_component(self, component_name: str, component_type: ComponentType) -> bool:
        """
        全局启用一个组件。

        Args:
            component_name: 组件名称
            component_type: 组件类型

        Returns:
            启用成功返回 True，失败返回 False
        """
        if component_type is ComponentType.ADAPTER:
            logger.error(f"组件 {component_name} 类型是适配器，无法启用或者禁用")
            return False
        target_class = self._registry.get_component_class(component_name, component_type)
        target_info = self._registry.get_component_info(component_name, component_type)
        if not target_class or not target_info:
            logger.warning(f"组件 {component_name} 未注册，无法启用")
            return False

        # 更新通用注册表中的状态
        target_info.enabled = True
        namespaced_name = f"{component_type.value}.{component_name}"
        self._registry._components[namespaced_name].enabled = True
        self._registry._components_by_type[component_type][component_name].enabled = True

        # 更新特定类型的启用列表
        match component_type:
            case ComponentType.ACTION:
                self._registry._default_actions[component_name] = target_info  # type: ignore
            case ComponentType.TOOL:
                self._registry._llm_available_tools[component_name] = target_class  # type: ignore
            case ComponentType.EVENT_HANDLER:
                self._registry._enabled_event_handlers[component_name] = target_class  # type: ignore
                # 重新注册事件处理器
                from .event_manager import event_manager
                event_manager.register_event_handler(
                    target_class,  # type: ignore
                    self._registry.get_plugin_config(target_info.plugin_name) or {}
                )
            case ComponentType.CHATTER:
                self._registry._enabled_chatter_registry[component_name] = target_class  # type: ignore
            case ComponentType.PROMPT:
                self._registry._enabled_prompt_registry[component_name] = target_class  # type: ignore
            case ComponentType.ADAPTER:
                self._registry._enabled_adapter_registry[component_name] = target_class  # type: ignore

        logger.info(f"组件 {component_name} ({component_type.value}) 已全局启用")
        return True

    async def disable_component(self, component_name: str, component_type: ComponentType) -> bool:
        """
        全局禁用一个组件。

        Args:
            component_name: 组件名称
            component_type: 组件类型

        Returns:
            禁用成功返回 True，失败返回 False
        """
        if component_type is ComponentType.ADAPTER:
            logger.error(f"组件 {component_name} 类型是适配器，无法启用或者禁用")
            return False
        target_info = self._registry.get_component_info(component_name, component_type)
        if not target_info:
            logger.warning(f"组件 {component_name} 未注册，无法禁用")
            return False

        # 更新通用注册表中的状态
        target_info.enabled = False
        namespaced_name = f"{component_type.value}.{component_name}"
        if namespaced_name in self._registry._components:
            self._registry._components[namespaced_name].enabled = False
        if component_name in self._registry._components_by_type[component_type]:
            self._registry._components_by_type[component_type][component_name].enabled = False

        try:
            # 从特定类型的启用列表中移除
            match component_type:
                case ComponentType.ACTION:
                    self._registry._default_actions.pop(component_name, None)
                case ComponentType.TOOL:
                    self._registry._llm_available_tools.pop(component_name, None)
                case ComponentType.EVENT_HANDLER:
                    self._registry._enabled_event_handlers.pop(component_name, None)
                    # 从事件管理器中取消订阅
                    from .event_manager import event_manager
                    event_manager.remove_event_handler(component_name)
                case ComponentType.CHATTER:
                    self._registry._enabled_chatter_registry.pop(component_name, None)
                case ComponentType.PROMPT:
                    self._registry._enabled_prompt_registry.pop(component_name, None)
                case ComponentType.ADAPTER:
                    self._registry._enabled_adapter_registry.pop(component_name, None)

            logger.info(f"组件 {component_name} ({component_type.value}) 已全局禁用")
            return True
        except Exception as e:
            logger.error(f"禁用组件时发生错误: {e}", exc_info=True)
            return False

    # =================================================================
    # == 局部状态管理 (Local State Management) - 用于会话级别控制
    # =================================================================

    def set_local_component_state(
        self, stream_id: str, component_name: str, component_type: ComponentType, enabled: bool
    ) -> bool:
        """
        为指定的会话（stream_id）设置组件的局部（临时）状态。

        这允许在单个对话流中动态启用或禁用组件，而不影响全局设置。

        Args:
            stream_id: 唯一的会话ID
            component_name: 组件名称
            component_type: 组件类型
            enabled: True 表示启用，False 表示禁用

        Returns:
            设置成功返回 True，如果组件类型不支持局部状态则返回 False
        """
        # 检查组件类型是否支持局部状态
        if component_type in self._no_local_state_types:
            logger.warning(f"组件类型 {component_type.value} 不支持局部状态管理")
            return False

        # 初始化该会话的状态字典（如果不存在）
        if stream_id not in self._local_component_states:
            self._local_component_states[stream_id] = {}

        # 设置局部状态
        self._local_component_states[stream_id][(component_name, component_type)] = enabled
        logger.debug(
            f"已为 stream '{stream_id}' 设置局部状态: "
            f"{component_name} ({component_type.value}) -> {'启用' if enabled else '禁用'}"
        )
        return True

    def clear_local_component_states(self, stream_id: str) -> None:
        """
        清除指定会话的所有局部状态。

        当会话结束时应调用此方法来清理资源。

        Args:
            stream_id: 要清除状态的会话ID
        """
        self._local_component_states.pop(stream_id, None)

    def get_local_state(
        self, stream_id: str, component_name: str, component_type: ComponentType
    ) -> bool | None:
        """
        获取指定会话中组件的局部状态。

        Args:
            stream_id: 会话ID
            component_name: 组件名称
            component_type: 组件类型

        Returns:
            局部状态值（True/False），如果没有设置则返回 None
        """
        if stream_id not in self._local_component_states:
            return None
        return self._local_component_states[stream_id].get((component_name, component_type))

    # =================================================================
    # == 组件可用性检查 (Component Availability Check)
    # =================================================================

    def is_component_available(
        self, component_name: str, component_type: ComponentType, stream_id: str | None = None
    ) -> bool:
        """
        检查一个组件在给定上下文中是否可用。

        检查顺序:
            1. 组件是否存在
            2. 组件所属插件是否已启用
            3. (如果提供了 stream_id 且组件类型支持局部状态) 是否有局部状态覆盖
            4. 全局启用状态

        Args:
            component_name: 组件名称
            component_type: 组件类型
            stream_id: 会话ID（可选）

        Returns:
            如果组件可用则返回 True
        """
        component_info = self._registry.get_component_info(component_name, component_type)

        # 1. 检查组件是否存在
        if not component_info:
            return False

        # 2. 检查组件所属插件是否已启用
        from src.plugin_system.core.plugin_manager import plugin_manager
        plugin_instance = plugin_manager.get_plugin_instance(component_info.plugin_name)
        if not plugin_instance:
            return False
        if not plugin_instance.enable_plugin:
            logger.debug(
                f"组件 {component_name} ({component_type.value}) 不可用: "
                f"所属插件 {component_info.plugin_name} 已被禁用"
            )
            return False

        # 3. 不支持局部状态的类型，直接返回全局状态
        if component_type in self._no_local_state_types:
            return component_info.enabled

        # 4. 如果提供了 stream_id，检查是否存在局部状态覆盖
        if stream_id:
            local_state = self.get_local_state(stream_id, component_name, component_type)
            if local_state is not None:
                return local_state  # 局部状态存在，直接返回

        # 5. 如果没有局部状态覆盖，返回全局状态
        return component_info.enabled

    def get_enabled_components_by_type(
        self, component_type: ComponentType, stream_id: str | None = None
    ) -> dict[str, ComponentInfo]:
        """
        获取指定类型的所有可用组件。

        这会同时考虑全局启用状态和 stream_id 对应的局部状态。

        Args:
            component_type: 要查询的组件类型
            stream_id: 会话ID，用于检查局部状态覆盖（可选）

        Returns:
            一个包含可用组件名称和信息的字典
        """
        return {
            name: info
            for name, info in self._registry.get_components_by_type(component_type).items()
            if self.is_component_available(name, component_type, stream_id)
        }

    # =================================================================
    # == 辅助方法 (Helper Methods)
    # =================================================================

    def supports_local_state(self, component_type: ComponentType) -> bool:
        """
        检查指定的组件类型是否支持局部状态管理。

        Args:
            component_type: 组件类型

        Returns:
            如果支持局部状态则返回 True
        """
        return component_type not in self._no_local_state_types

    def get_all_local_states(self) -> dict[str, dict[tuple[str, ComponentType], bool]]:
        """
        获取所有会话的局部状态（用于调试）。

        Returns:
            所有局部状态的字典（副本）
        """
        return {
            stream_id: states.copy()
            for stream_id, states in self._local_component_states.items()
        }
