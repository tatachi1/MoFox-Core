"""
Plugin Info API
===============

该模块提供了用于查询插件和组件信息、生成报告和统计数据的API。

主要功能包括：
- 系统状态报告生成
- 插件详情查询
- 组件列表和搜索
- 状态统计
- 工具函数
"""

from typing import Any, Literal

from src.common.logger import get_logger
from src.plugin_system.base.component_types import ComponentType
from src.plugin_system.core.component_registry import ComponentInfo, component_registry
from src.plugin_system.core.plugin_manager import plugin_manager

# 初始化日志记录器
logger = get_logger("plugin_info_api")


# --------------------------------------------------------------------------------
# Section 1: 信息查询与报告 (Information Querying & Reporting)
# --------------------------------------------------------------------------------
# 这部分 API 用于获取关于插件和组件的详细信息、列表和统计数据。


def get_system_report() -> dict[str, Any]:
    """
    生成一份详细的系统状态报告。

    报告包含已加载插件、失败插件和组件的全面信息，是调试和监控系统状态的核心工具。

    Returns:
        dict[str, Any]: 包含系统、插件和组件状态的详细报告字典。
    """
    loaded_plugins_info = {}
    # 遍历所有已加载的插件实例
    for name, instance in plugin_manager.loaded_plugins.items():
        plugin_info = component_registry.get_plugin_info(name)
        if not plugin_info:
            continue

        # 收集该插件下所有组件的详细信息
        components_details = [
            {
                "name": comp_info.name,
                "component_type": comp_info.component_type.value,
                "description": comp_info.description,
                "enabled": comp_info.enabled,
            }
            for comp_info in plugin_info.components
        ]

        # 构建单个插件的信息字典
        # 元数据从 PluginInfo 获取，而启用状态(enable_plugin)从插件实例获取
        loaded_plugins_info[name] = {
            "display_name": plugin_info.display_name or name,
            "version": plugin_info.version,
            "author": plugin_info.author,
            "enabled": instance.enable_plugin,
            "components": components_details,
        }

    # 构建最终的完整报告
    report = {
        "system_info": {
            "loaded_plugins_count": len(plugin_manager.loaded_plugins),
            "total_components_count": component_registry.get_registry_stats().get("total_components", 0),
        },
        "plugins": loaded_plugins_info,
        "failed_plugins": plugin_manager.failed_plugins,
    }
    return report


def get_plugin_details(plugin_name: str) -> dict[str, Any] | None:
    """
    获取单个插件的详细报告。

    报告内容包括插件的元数据、所有组件的详细信息及其当前状态。
    这是 `get_system_report` 的单插件聚焦版本。

    Args:
        plugin_name (str): 要查询的插件名称。

    Returns:
        dict | None: 包含插件详细信息的字典，如果插件未注册则返回 None。
    """
    plugin_info = component_registry.get_plugin_info(plugin_name)
    if not plugin_info:
        logger.warning(f"尝试获取插件详情失败：未找到名为 '{plugin_name}' 的插件。")
        return None

    # 收集该插件下所有组件的信息
    components_details = [
        {
            "name": comp_info.name,
            "component_type": comp_info.component_type.value,
            "description": comp_info.description,
            "enabled": comp_info.enabled,
        }
        for comp_info in plugin_info.components
    ]

    # 获取插件实例以检查其启用状态
    plugin_instance = plugin_manager.get_plugin_instance(plugin_name)
    is_enabled = plugin_instance.enable_plugin if plugin_instance else False

    # 组装详细信息字典
    return {
        "name": plugin_info.name,
        "display_name": plugin_info.display_name or plugin_info.name,
        "version": plugin_info.version,
        "author": plugin_info.author,
        "license": plugin_info.license,
        "description": plugin_info.description,
        "enabled": is_enabled,
        "status": "loaded" if is_plugin_loaded(plugin_name) else "registered",
        "components": components_details,
    }


def list_plugins(status: Literal["loaded", "registered", "failed"]) -> list[str]:
    """
    根据指定的状态列出插件名称列表。

    提供了一种快速、便捷的方式来监控和调试插件系统，而无需解析完整的系统报告。

    Args:
        status (str): 插件状态，可选值为 'loaded', 'registered', 'failed'。

    Returns:
        list[str]: 对应状态的插件名称列表。

    Raises:
        ValueError: 如果传入了无效的状态字符串。
    """
    if status == "loaded":
        # 返回所有当前已成功加载的插件
        return plugin_manager.list_loaded_plugins()
    if status == "registered":
        # 返回所有已注册（但不一定已加载）的插件
        return plugin_manager.list_registered_plugins()
    if status == "failed":
        # 返回所有加载失败的插件的名称
        return list(plugin_manager.failed_plugins.keys())
    # 如果状态无效，则引发错误
    raise ValueError(f"无效的插件状态: '{status}'。有效选项为 'loaded', 'registered', 'failed'。")


def list_components(component_type: ComponentType, enabled_only: bool = True) -> list[dict[str, Any]]:
    """
    列出指定类型的所有组件的详细信息。

    这是查找和管理组件的核心功能，例如，获取所有可用的工具或所有注册的聊天器。

    Args:
        component_type (ComponentType): 要查询的组件类型。
        enabled_only (bool, optional): 是否只返回已启用的组件。默认为 True。

    Returns:
        list[dict[str, Any]]: 一个包含组件信息字典的列表。
    """
    # 根据 enabled_only 参数决定是获取所有组件还是仅获取已启用的组件
    if enabled_only:
        components = component_registry.get_enabled_components_by_type(component_type)
    else:
        components = component_registry.get_components_by_type(component_type)

    # 将组件信息格式化为字典列表
    return [
        {
            "name": info.name,
            "plugin_name": info.plugin_name,
            "description": info.description,
            "enabled": info.enabled,
        }
        for info in components.values()
    ]


def search_components_by_name(
    name_keyword: str,
    component_type: ComponentType | None = None,
    case_sensitive: bool = False,
    exact_match: bool = False,
) -> list[dict[str, Any]]:
    """
    根据名称关键字搜索组件，支持模糊匹配和精确匹配。

    极大地增强了组件的可发现性，用户无需知道完整名称即可找到所需组件。

    Args:
        name_keyword (str): 用于搜索的名称关键字。
        component_type (ComponentType | None, optional): 如果提供，则只在该类型中搜索。默认为 None (搜索所有类型)。
        case_sensitive (bool, optional): 是否进行大小写敏感的搜索。默认为 False。
        exact_match (bool, optional): 是否进行精确匹配。默认为 False (模糊匹配)。

    Returns:
        list[dict[str, Any]]: 匹配的组件信息字典的列表。
    """
    results = []
    # 如果未指定组件类型，则搜索所有类型
    types_to_search = [component_type] if component_type else list(ComponentType)

    # 根据是否大小写敏感，预处理搜索关键字
    compare_str = name_keyword if case_sensitive else name_keyword.lower()

    # 遍历要搜索的组件类型
    for comp_type in types_to_search:
        all_components = component_registry.get_components_by_type(comp_type)
        for name, info in all_components.items():
            # 同样地，预处理组件名称
            target_name = name if case_sensitive else name.lower()

            # 根据 exact_match 参数决定使用精确比较还是模糊包含检查
            is_match = (compare_str == target_name) if exact_match else (compare_str in target_name)

            # 如果匹配，则将组件信息添加到结果列表
            if is_match:
                results.append(
                    {
                        "name": info.name,
                        "component_type": info.component_type.value,
                        "plugin_name": info.plugin_name,
                        "description": info.description,
                        "enabled": info.enabled,
                    }
                )
    return results


def get_component_info(name: str, component_type: ComponentType) -> ComponentInfo | None:
    """
    获取任何一个已注册组件的详细信息对象。

    Args:
        name (str): 组件的唯一名称。
        component_type (ComponentType): 组件的类型。

    Returns:
        ComponentInfo | None: 包含组件完整信息的 ComponentInfo 对象，如果找不到则返回 None。
    """
    return component_registry.get_component_info(name, component_type)


# --------------------------------------------------------------------------------
# Section 2: 状态查询与统计 (State Querying & Statistics)
# --------------------------------------------------------------------------------
# 这部分 API 提供状态查询和统计功能。


def get_plugin_state(plugin_name: str) -> dict[str, Any] | None:
    """
    获取插件的详细状态信息。

    Args:
        plugin_name (str): 要查询的插件名称。

    Returns:
        dict | None: 包含插件状态信息的字典，如果插件不存在则返回 None。
    """
    plugin_instance = plugin_manager.get_plugin_instance(plugin_name)
    plugin_info = component_registry.get_plugin_info(plugin_name)

    if not plugin_info:
        return None

    is_loaded = plugin_name in plugin_manager.list_loaded_plugins()
    is_enabled = plugin_instance.enable_plugin if plugin_instance else False

    # 统计组件状态
    total_components = len(plugin_info.components)
    enabled_components = sum(1 for c in plugin_info.components if c.enabled)

    return {
        "name": plugin_name,
        "is_loaded": is_loaded,
        "is_enabled": is_enabled,
        "total_components": total_components,
        "enabled_components": enabled_components,
        "disabled_components": total_components - enabled_components,
    }


def get_all_plugin_states() -> dict[str, dict[str, Any]]:
    """
    获取所有已加载插件的状态信息。

    Returns:
        dict: 插件名称到状态信息的映射。
    """
    result = {}
    for plugin_name in plugin_manager.list_loaded_plugins():
        state = get_plugin_state(plugin_name)
        if state:
            result[plugin_name] = state
    return result


def get_state_statistics() -> dict[str, Any]:
    """
    获取整体状态统计信息。

    Returns:
        dict: 包含插件和组件状态统计的字典。
    """
    loaded_plugins = plugin_manager.list_loaded_plugins()
    registered_plugins = plugin_manager.list_registered_plugins()
    failed_plugins = list(plugin_manager.failed_plugins.keys())

    # 统计启用/禁用的插件数量
    enabled_plugins = sum(1 for name in loaded_plugins if is_plugin_enabled(name))

    # 统计各类型组件数量
    component_stats = {}
    total_enabled = 0
    total_disabled = 0

    for comp_type in ComponentType:
        all_components = component_registry.get_components_by_type(comp_type)
        enabled_count = sum(1 for info in all_components.values() if info.enabled)
        disabled_count = len(all_components) - enabled_count

        component_stats[comp_type.value] = {
            "total": len(all_components),
            "enabled": enabled_count,
            "disabled": disabled_count,
        }
        total_enabled += enabled_count
        total_disabled += disabled_count

    return {
        "plugins": {
            "loaded": len(loaded_plugins),
            "registered": len(registered_plugins),
            "failed": len(failed_plugins),
            "enabled": enabled_plugins,
            "disabled": len(loaded_plugins) - enabled_plugins,
        },
        "components": {
            "total": total_enabled + total_disabled,
            "enabled": total_enabled,
            "disabled": total_disabled,
            "by_type": component_stats,
        },
    }


# --------------------------------------------------------------------------------
# Section 3: 工具函数 (Utility Functions)
# --------------------------------------------------------------------------------
# 这部分提供了一些轻量级的辅助函数，用于快速检查状态。


def is_plugin_loaded(plugin_name: str) -> bool:
    """
    快速检查一个插件当前是否已成功加载。

    这是一个比 `get_plugin_details` 更轻量级的检查方法，适用于需要快速布尔值判断的场景。

    Args:
        plugin_name (str): 要检查的插件名称。

    Returns:
        bool: 如果插件已加载，则为 True，否则为 False。
    """
    return plugin_name in plugin_manager.list_loaded_plugins()


def is_plugin_enabled(plugin_name: str) -> bool:
    """
    检查插件是否处于启用状态。

    Args:
        plugin_name (str): 要检查的插件名称。

    Returns:
        bool: 如果插件已启用，则为 True；如果未加载或已禁用，则为 False。
    """
    plugin_instance = plugin_manager.get_plugin_instance(plugin_name)
    if not plugin_instance:
        return False
    return plugin_instance.enable_plugin


def get_component_plugin(component_name: str, component_type: ComponentType) -> str | None:
    """
    查找一个特定组件属于哪个插件。

    在调试或管理组件时，此函数能够方便地追溯其定义的源头。

    Args:
        component_name (str): 组件的名称。
        component_type (ComponentType): 组件的类型。

    Returns:
        str | None: 组件所属的插件名称，如果找不到组件则返回 None。
    """
    component_info = component_registry.get_component_info(component_name, component_type)
    return component_info.plugin_name if component_info else None


def validate_component_exists(name: str, component_type: ComponentType) -> bool:
    """
    验证组件是否存在于注册表中。

    Args:
        name (str): 组件名称。
        component_type (ComponentType): 组件类型。

    Returns:
        bool: 如果组件存在，则为 True。
    """
    return component_registry.get_component_info(name, component_type) is not None


def get_plugin_component_summary(plugin_name: str) -> dict[str, Any] | None:
    """
    获取插件的组件摘要信息。

    Args:
        plugin_name (str): 插件名称。

    Returns:
        dict | None: 包含组件摘要的字典，如果插件不存在则返回 None。
    """
    plugin_info = component_registry.get_plugin_info(plugin_name)
    if not plugin_info:
        return None

    # 按类型统计组件
    by_type = {}
    for comp_type in ComponentType:
        components = [c for c in plugin_info.components if c.component_type == comp_type]
        if components:
            enabled = sum(1 for c in components if c.enabled)
            by_type[comp_type.value] = {
                "total": len(components),
                "enabled": enabled,
                "disabled": len(components) - enabled,
                "names": [c.name for c in components],
            }

    return {
        "plugin_name": plugin_name,
        "total_components": len(plugin_info.components),
        "by_type": by_type,
    }
