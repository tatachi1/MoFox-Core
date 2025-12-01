"""
Component State API
===================

该模块提供了用于管理组件启用/禁用状态的核心API。
支持全局和局部（临时）范围的组件状态控制，以及批量操作。

主要功能包括：
- 组件的全局和局部启用/禁用
- 批量组件状态管理
- 组件状态查询
"""

from typing import Any

from src.common.logger import get_logger
from src.plugin_system.base.component_types import ComponentType
from src.plugin_system.core.component_registry import ComponentInfo, component_registry

# 初始化日志记录器
logger = get_logger("component_state_api")


# --------------------------------------------------------------------------------
# Section 1: 组件状态管理 (Component State Management)
# --------------------------------------------------------------------------------
# 这部分 API 负责控制单个组件的启用和禁用状态，支持全局和局部（临时）范围。


async def set_component_enabled(name: str, component_type: ComponentType, enabled: bool) -> bool:
    """
    在全局范围内启用或禁用一个组件。

    此更改会直接修改组件在注册表中的状态，但此状态是临时的，不会持久化到配置文件中。
    包含一个保护机制，防止禁用最后一个已启用的 Chatter 组件。

    Args:
        name (str): 要操作的组件的名称。
        component_type (ComponentType): 组件的类型。
        enabled (bool): True 表示启用, False 表示禁用。

    Returns:
        bool: 如果操作成功，则为 True。
    """
    # 特殊保护：确保系统中至少有一个 Chatter 组件处于启用状态
    if component_type == ComponentType.CHATTER and not enabled:
        enabled_chatters = component_registry.get_enabled_components_by_type(ComponentType.CHATTER)
        if len(enabled_chatters) <= 1 and name in enabled_chatters:
            logger.warning(f"操作被阻止：不能禁用最后一个启用的 Chatter 组件 ('{name}')。")
            return False

    # 根据 enabled 参数调用相应的注册表方法
    if enabled:
        return component_registry.enable_component(name, component_type)
    else:
        return await component_registry.disable_component(name, component_type)


def set_component_enabled_local(stream_id: str, name: str, component_type: ComponentType, enabled: bool) -> bool:
    """
    在一个特定的 stream_id 上下文中临时启用或禁用组件。

    此状态仅存在于内存中，并且只对指定的 stream_id 有效，不影响全局组件状态。
    同样包含对 Chatter 组件的保护机制。

    Args:
        stream_id (str): 唯一的上下文标识符，例如一个会话ID。
        name (str): 组件名称。
        component_type (ComponentType): 组件类型。
        enabled (bool): True 为启用, False 为禁用。

    Returns:
        bool: 如果操作成功，则为 True。
    """
    # 首先，验证组件是否存在
    component_info = component_registry.get_component_info(name, component_type)
    if not component_info:
        logger.error(f"尝试设置局部状态失败：未找到组件 {name} ({component_type.value})。")
        return False

    # Chatter 唯一性保护（在 stream_id 上下文中）
    if component_type == ComponentType.CHATTER and not enabled:
        enabled_chatters = component_registry.get_enabled_components_by_type(ComponentType.CHATTER, stream_id=stream_id)
        if len(enabled_chatters) <= 1 and name in enabled_chatters:
            logger.warning(f"操作被阻止：在 stream '{stream_id}' 中，不能禁用最后一个启用的 Chatter 组件 ('{name}')。")
            return False

    # 设置局部状态
    component_registry.set_local_component_state(stream_id, name, component_type, enabled)
    logger.info(f"在 stream '{stream_id}' 中，组件 {name} ({component_type.value}) 的局部状态已设置为: {enabled}")
    return True


def clear_local_component_states(stream_id: str) -> None:
    """
    清除指定会话的所有局部组件状态。

    当会话结束时应调用此方法来清理资源。

    Args:
        stream_id (str): 要清除状态的会话ID。
    """
    component_registry.clear_local_component_states(stream_id)
    logger.debug(f"已清除 stream '{stream_id}' 的所有局部组件状态。")


def is_component_enabled(name: str, component_type: ComponentType, stream_id: str | None = None) -> bool:
    """
    检查组件是否在指定上下文中启用。

    Args:
        name (str): 组件名称。
        component_type (ComponentType): 组件类型。
        stream_id (str | None): 可选的会话ID，用于检查局部状态。

    Returns:
        bool: 如果组件启用，则为 True。
    """
    return component_registry.is_component_available(name, component_type, stream_id)


def get_component_state(name: str, component_type: ComponentType) -> dict[str, Any] | None:
    """
    获取组件的详细状态信息。

    Args:
        name (str): 组件名称。
        component_type (ComponentType): 组件类型。

    Returns:
        dict | None: 包含组件状态信息的字典，如果组件不存在则返回 None。
    """
    component_info = component_registry.get_component_info(name, component_type)
    if not component_info:
        return None

    return {
        "name": component_info.name,
        "component_type": component_info.component_type.value,
        "plugin_name": component_info.plugin_name,
        "enabled": component_info.enabled,
        "description": component_info.description,
    }


# --------------------------------------------------------------------------------
# Section 2: 批量组件状态管理 (Batch Component State Management)
# --------------------------------------------------------------------------------
# 这部分 API 提供批量操作组件状态的功能。


async def enable_all_plugin_components(plugin_name: str) -> dict[str, bool]:
    """
    启用指定插件下的所有组件。

    Args:
        plugin_name (str): 插件名称。

    Returns:
        dict[str, bool]: 每个组件名称及其启用操作是否成功的字典。
    """
    plugin_info = component_registry.get_plugin_info(plugin_name)
    if not plugin_info:
        logger.error(f"未找到插件 '{plugin_name}'，无法启用其组件。")
        return {}

    results = {}
    for component_info in plugin_info.components:
        success = component_registry.enable_component(component_info.name, component_info.component_type)
        results[component_info.name] = success
        if success:
            logger.debug(f"已启用组件: {component_info.name} ({component_info.component_type.value})")
        else:
            logger.warning(f"启用组件失败: {component_info.name} ({component_info.component_type.value})")

    logger.info(f"已完成启用插件 '{plugin_name}' 的所有组件，成功: {sum(results.values())}/{len(results)}")
    return results


async def disable_all_plugin_components(plugin_name: str) -> dict[str, bool]:
    """
    禁用指定插件下的所有组件。

    包含对 Chatter 组件的保护机制。

    Args:
        plugin_name (str): 插件名称。

    Returns:
        dict[str, bool]: 每个组件名称及其禁用操作是否成功的字典。
    """
    plugin_info = component_registry.get_plugin_info(plugin_name)
    if not plugin_info:
        logger.error(f"未找到插件 '{plugin_name}'，无法禁用其组件。")
        return {}

    results = {}
    for component_info in plugin_info.components:
        # Chatter 保护检查
        if component_info.component_type == ComponentType.CHATTER:
            enabled_chatters = component_registry.get_enabled_components_by_type(ComponentType.CHATTER)
            if len(enabled_chatters) <= 1 and component_info.name in enabled_chatters:
                logger.warning(
                    f"跳过禁用最后一个 Chatter 组件 '{component_info.name}'，系统至少需要一个启用的 Chatter。"
                )
                results[component_info.name] = False
                continue

        success = await component_registry.disable_component(component_info.name, component_info.component_type)
        results[component_info.name] = success
        if success:
            logger.debug(f"已禁用组件: {component_info.name} ({component_info.component_type.value})")
        else:
            logger.warning(f"禁用组件失败: {component_info.name} ({component_info.component_type.value})")

    logger.info(f"已完成禁用插件 '{plugin_name}' 的所有组件，成功: {sum(results.values())}/{len(results)}")
    return results


async def set_components_enabled_by_type(
    plugin_name: str, component_type: ComponentType, enabled: bool
) -> dict[str, bool]:
    """
    启用或禁用指定插件下特定类型的所有组件。

    Args:
        plugin_name (str): 插件名称。
        component_type (ComponentType): 要操作的组件类型。
        enabled (bool): True 为启用，False 为禁用。

    Returns:
        dict[str, bool]: 每个组件名称及其操作是否成功的字典。
    """
    plugin_info = component_registry.get_plugin_info(plugin_name)
    if not plugin_info:
        logger.error(f"未找到插件 '{plugin_name}'。")
        return {}

    results = {}
    for component_info in plugin_info.components:
        if component_info.component_type != component_type:
            continue

        success = await set_component_enabled(component_info.name, component_type, enabled)
        results[component_info.name] = success

    action = "启用" if enabled else "禁用"
    logger.info(
        f"已完成{action}插件 '{plugin_name}' 的所有 {component_type.value} 组件，"
        f"成功: {sum(results.values())}/{len(results)}"
    )
    return results


async def batch_set_components_enabled(components: list[tuple[str, ComponentType]], enabled: bool) -> dict[str, bool]:
    """
    批量启用或禁用多个组件。

    Args:
        components (list[tuple[str, ComponentType]]): 要操作的组件列表，
            每个元素为 (组件名称, 组件类型) 元组。
        enabled (bool): True 为启用，False 为禁用。

    Returns:
        dict[str, bool]: 每个组件名称及其操作是否成功的字典。
    """
    results = {}
    for name, component_type in components:
        success = await set_component_enabled(name, component_type, enabled)
        results[name] = success

    action = "启用" if enabled else "禁用"
    logger.info(f"批量{action}操作完成，成功: {sum(results.values())}/{len(results)}")
    return results


# --------------------------------------------------------------------------------
# Section 3: 组件状态查询与筛选 (Component State Query & Filter)
# --------------------------------------------------------------------------------
# 这部分 API 提供组件状态的查询和筛选功能。


def get_components_by_state(
    component_type: ComponentType | None = None,
    enabled: bool | None = None,
    plugin_name: str | None = None,
) -> list[ComponentInfo]:
    """
    根据条件筛选组件。

    Args:
        component_type (ComponentType | None): 按组件类型筛选。
        enabled (bool | None): 按启用状态筛选。
        plugin_name (str | None): 按插件名称筛选。

    Returns:
        list[ComponentInfo]: 符合条件的组件信息列表。
    """
    results = []

    # 确定要搜索的组件类型
    types_to_search = [component_type] if component_type else list(ComponentType)

    for comp_type in types_to_search:
        components = component_registry.get_components_by_type(comp_type)
        for info in components.values():
            # 按启用状态筛选
            if enabled is not None and info.enabled != enabled:
                continue
            # 按插件名称筛选
            if plugin_name is not None and info.plugin_name != plugin_name:
                continue
            results.append(info)

    return results


def get_disabled_components(plugin_name: str | None = None) -> list[ComponentInfo]:
    """
    获取所有被禁用的组件。

    Args:
        plugin_name (str | None): 可选，仅获取指定插件的禁用组件。

    Returns:
        list[ComponentInfo]: 禁用组件的信息列表。
    """
    return get_components_by_state(enabled=False, plugin_name=plugin_name)


def get_enabled_components(plugin_name: str | None = None) -> list[ComponentInfo]:
    """
    获取所有已启用的组件。

    Args:
        plugin_name (str | None): 可选，仅获取指定插件的启用组件。

    Returns:
        list[ComponentInfo]: 启用组件的信息列表。
    """
    return get_components_by_state(enabled=True, plugin_name=plugin_name)


def get_component_count(component_type: ComponentType, stream_id: str | None = None) -> int:
    """
    获取指定类型的已加载并启用的组件的总数。

    可以根据 `stream_id` 考虑局部状态，从而获得特定上下文中的组件数量。

    Args:
        component_type (ComponentType): 要查询的组件类型。
        stream_id (str | None): 可选的上下文ID。如果提供，将计入局部状态。

    Returns:
        int: 该类型下已启用的组件的数量。
    """
    return len(component_registry.get_enabled_components_by_type(component_type, stream_id=stream_id))
