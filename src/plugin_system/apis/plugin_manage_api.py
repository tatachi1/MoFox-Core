# -*- coding: utf-8 -*-
import os
from typing import Any

from src.common.logger import get_logger
from src.plugin_system.base.component_types import ComponentType
from src.plugin_system.core.component_registry import ComponentInfo, component_registry
from src.plugin_system.core.plugin_manager import plugin_manager

logger = get_logger("plugin_manage_api")


async def reload_all_plugins() -> bool:
    """
    重新加载所有当前已成功加载的插件。

    此操作会先卸载所有插件，然后重新加载它们。

    Returns:
        bool: 如果所有插件都成功重载，则为 True，否则为 False。
    """
    logger.info("开始重新加载所有插件...")
    # 使用 list() 复制一份列表，防止在迭代时修改原始列表
    loaded_plugins = list(plugin_manager.list_loaded_plugins())
    all_success = True

    for plugin_name in loaded_plugins:
        try:
            success = await reload_plugin(plugin_name)
            if not success:
                all_success = False
                logger.error(f"重载插件 {plugin_name} 失败。")
        except Exception as e:
            all_success = False
            logger.error(f"重载插件 {plugin_name} 时发生异常: {e}", exc_info=True)

    logger.info("所有插件重载完毕。")
    return all_success


async def reload_plugin(name: str) -> bool:
    """
    重新加载指定的单个插件。

    Args:
        name (str): 要重载的插件的名称。

    Returns:
        bool: 成功则为 True。

    Raises:
        ValueError: 如果插件未找到。
    """
    if name not in plugin_manager.list_registered_plugins():
        raise ValueError(f"插件 '{name}' 未注册。")
    return await plugin_manager.reload_registered_plugin(name)


async def set_component_enabled(name: str, component_type: ComponentType, enabled: bool) -> bool:
    """
    全局范围内启用或禁用一个组件。

    此更改会更新组件注册表中的状态，但不会持久化到文件。

    Args:
        name (str): 组件名称。
        component_type (ComponentType): 组件类型。
        enabled (bool): True 为启用, False 为禁用。

    Returns:
        bool: 操作成功则为 True。
    """
    # Chatter 唯一性保护
    if component_type == ComponentType.CHATTER and not enabled:
        enabled_chatters = component_registry.get_enabled_components_by_type(ComponentType.CHATTER)
        if len(enabled_chatters) <= 1 and name in enabled_chatters:
            logger.warning(f"操作被阻止：不能禁用最后一个启用的 Chatter 组件 ('{name}')。")
            return False

    # 注意：这里我们直接修改 ComponentInfo 中的状态
    component_info = component_registry.get_component_info(name, component_type)
    if not component_info:
        logger.error(f"未找到组件 {name} ({component_type.value})，无法更改其状态。")
        return False
    component_info.enabled = enabled
    logger.info(f"组件 {name} ({component_type.value}) 的全局状态已设置为: {enabled}")
    return True


def set_component_enabled_local(stream_id: str, name: str, component_type: ComponentType, enabled: bool) -> bool:
    """
    在一个特定的 stream_id 上下文中临时启用或禁用组件。

    此状态仅存于内存，不影响全局状态。

    Args:
        stream_id (str): 上下文标识符。
        name (str): 组件名称。
        component_type (ComponentType): 组件类型。
        enabled (bool): True 为启用, False 为禁用。

    Returns:
        bool: 操作成功则为 True。
    """
    component_registry.set_local_component_state(stream_id, name, component_type, enabled)
    return True


def rescan_and_register_plugins(load_after_register: bool = True) -> tuple[int, int]:
    """
    重新扫描所有插件目录，发现新插件并注册。

    Args:
        load_after_register (bool): 如果为 True，新发现的插件将在注册后立即被加载。

    Returns:
        Tuple[int, int]: (成功数量, 失败数量)
    """
    success_count, fail_count = plugin_manager.rescan_plugin_directory()
    if not load_after_register:
        return success_count, fail_count

    newly_registered = [
        p for p in plugin_manager.list_registered_plugins() if p not in plugin_manager.list_loaded_plugins()
    ]
    loaded_success = 0
    for plugin_name in newly_registered:
        status, _ = plugin_manager.load_registered_plugin_classes(plugin_name)
        if status:
            loaded_success += 1

    return loaded_success, fail_count + (len(newly_registered) - loaded_success)


def register_plugin_from_file(plugin_name: str, load_after_register: bool = True) -> bool:
    """
    从默认插件目录中查找、注册并加载一个插件。

    Args:
        plugin_name (str): 插件的名称（即其目录名）。
        load_after_register (bool): 注册后是否立即加载。

    Returns:
        bool: 成功则为 True。
    """
    if plugin_name in plugin_manager.list_loaded_plugins():
        logger.warning(f"插件 '{plugin_name}' 已经加载。")
        return True

    # 如果插件未注册，则遍历插件目录去查找
    if plugin_name not in plugin_manager.list_registered_plugins():
        logger.info(f"插件 '{plugin_name}' 未注册，开始在插件目录中搜索...")
        found_path = None
        for directory in plugin_manager.plugin_directories:
            potential_path = os.path.join(directory, plugin_name)
            if os.path.isdir(potential_path):
                found_path = potential_path
                break

        if not found_path:
            logger.error(f"在所有插件目录中都未找到名为 '{plugin_name}' 的插件。")
            return False

        plugin_file = os.path.join(found_path, "plugin.py")
        if not os.path.exists(plugin_file):
            logger.error(f"在 '{found_path}' 中未找到 plugin.py 文件。")
            return False

        module = plugin_manager._load_plugin_module_file(plugin_file)
        if not module:
            logger.error(f"从 '{plugin_file}' 加载插件模块失败。")
            return False

        if plugin_name not in plugin_manager.list_registered_plugins():
            logger.error(f"插件 '{plugin_name}' 在加载模块后依然未注册成功。")
            return False
        
        logger.info(f"插件 '{plugin_name}' 已成功发现并注册。")

    if load_after_register:
        status, _ = plugin_manager.load_registered_plugin_classes(plugin_name)
        return status
    return True


def get_component_count(component_type: ComponentType, stream_id: str | None = None) -> int:
    """
    获取指定类型的已加载并启用的组件的总数。

    可以根据 stream_id 考虑局部状态。

    Args:
        component_type (ComponentType): 要查询的组件类型。
        stream_id (str | None): 可选的上下文ID。

    Returns:
        int: 该类型组件的数量。
    """
    return len(component_registry.get_enabled_components_by_type(component_type, stream_id=stream_id))


def get_component_info(name: str, component_type: ComponentType) -> ComponentInfo | None:
    """
    获取任何一个已注册组件的详细信息。

    Args:
        name (str): 组件的唯一名称。
        component_type (ComponentType): 组件的类型。

    Returns:
        ComponentInfo: 包含组件信息的对象，如果找不到则返回 None。
    """
    return component_registry.get_component_info(name, component_type)


def get_system_report() -> dict[str, Any]:
    """
    生成一份详细的系统状态报告。

    Returns:
        dict: 包含系统、插件和组件状态的详细报告。
    """
    loaded_plugins_info = {}
    for name, instance in plugin_manager.loaded_plugins.items():
        plugin_info = component_registry.get_plugin_info(name)
        if not plugin_info:
            continue

        components_details = []
        for comp_info in plugin_info.components:
            components_details.append(
                {
                    "name": comp_info.name,
                    "component_type": comp_info.component_type.value,
                    "description": comp_info.description,
                    "enabled": comp_info.enabled,
                }
            )
        
        # 从 plugin_info (PluginInfo) 而不是 instance (PluginBase) 获取元数据
        loaded_plugins_info[name] = {
            "display_name": plugin_info.display_name or name,
            "version": plugin_info.version,
            "author": plugin_info.author,
            "enabled": instance.enable_plugin, # enable_plugin 状态还是需要从实例获取
            "components": components_details,
        }

    report = {
        "system_info": {
            "loaded_plugins_count": len(plugin_manager.loaded_plugins),
            "total_components_count": component_registry.get_registry_stats().get("total_components", 0),
        },
        "plugins": loaded_plugins_info,
        "failed_plugins": plugin_manager.failed_plugins,
    }
    return report
