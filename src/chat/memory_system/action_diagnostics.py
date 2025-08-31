#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Action组件诊断和修复脚本
检查no_reply等核心Action是否正确注册，并尝试修复相关问题
"""

import sys
import os
from typing import Dict, Any

# 添加项目路径
sys.path.append(os.path.join(os.path.dirname(__file__), "../../../"))

from src.common.logger import get_logger
from src.plugin_system.core.component_registry import component_registry
from src.plugin_system.core.plugin_manager import plugin_manager
from src.plugin_system.base.component_types import ComponentType

logger = get_logger("action_diagnostics")


class ActionDiagnostics:
    """Action组件诊断器"""

    def __init__(self):
        self.required_actions = ["no_reply", "reply", "emoji", "at_user"]

    def check_plugin_loading(self) -> Dict[str, Any]:
        """检查插件加载状态"""
        logger.info("开始检查插件加载状态...")

        result = {
            "plugins_loaded": False,
            "total_plugins": 0,
            "loaded_plugins": [],
            "failed_plugins": [],
            "core_actions_plugin": None,
        }

        try:
            # 加载所有插件
            plugin_manager.load_all_plugins()

            # 获取插件统计信息
            stats = plugin_manager.get_stats()
            result["plugins_loaded"] = True
            result["total_plugins"] = stats.get("total_plugins", 0)

            # 检查是否有core_actions插件
            for plugin_name in plugin_manager.loaded_plugins:
                result["loaded_plugins"].append(plugin_name)
                if "core_actions" in plugin_name.lower():
                    result["core_actions_plugin"] = plugin_name

            logger.info(f"插件加载成功，总数: {result['total_plugins']}")
            logger.info(f"已加载插件: {result['loaded_plugins']}")

        except Exception as e:
            logger.error(f"插件加载失败: {e}")
            result["error"] = str(e)

        return result

    def check_action_registry(self) -> Dict[str, Any]:
        """检查Action注册状态"""
        logger.info("开始检查Action组件注册状态...")

        result = {"registered_actions": [], "missing_actions": [], "default_actions": {}, "total_actions": 0}

        try:
            # 获取所有注册的Action
            all_components = component_registry.get_all_components(ComponentType.ACTION)
            result["total_actions"] = len(all_components)

            for name, info in all_components.items():
                result["registered_actions"].append(name)
                logger.debug(f"已注册Action: {name} (插件: {info.plugin_name})")

            # 检查必需的Action是否存在
            for required_action in self.required_actions:
                if required_action not in all_components:
                    result["missing_actions"].append(required_action)
                    logger.warning(f"缺失必需Action: {required_action}")
                else:
                    logger.info(f"找到必需Action: {required_action}")

            # 获取默认Action
            default_actions = component_registry.get_default_actions()
            result["default_actions"] = {name: info.plugin_name for name, info in default_actions.items()}

            logger.info(f"总注册Action数量: {result['total_actions']}")
            logger.info(f"缺失Action: {result['missing_actions']}")

        except Exception as e:
            logger.error(f"Action注册检查失败: {e}")
            result["error"] = str(e)

        return result

    def check_specific_action(self, action_name: str) -> Dict[str, Any]:
        """检查特定Action的详细信息"""
        logger.info(f"检查Action详细信息: {action_name}")

        result = {
            "exists": False,
            "component_info": None,
            "component_class": None,
            "is_default": False,
            "plugin_name": None,
        }

        try:
            # 检查组件信息
            component_info = component_registry.get_component_info(action_name, ComponentType.ACTION)
            if component_info:
                result["exists"] = True
                result["component_info"] = {
                    "name": component_info.name,
                    "description": component_info.description,
                    "plugin_name": component_info.plugin_name,
                    "version": component_info.version,
                }
                result["plugin_name"] = component_info.plugin_name
                logger.info(f"找到Action组件信息: {action_name}")
            else:
                logger.warning(f"未找到Action组件信息: {action_name}")
                return result

            # 检查组件类
            component_class = component_registry.get_component_class(action_name, ComponentType.ACTION)
            if component_class:
                result["component_class"] = component_class.__name__
                logger.info(f"找到Action组件类: {component_class.__name__}")
            else:
                logger.warning(f"未找到Action组件类: {action_name}")

            # 检查是否为默认Action
            default_actions = component_registry.get_default_actions()
            result["is_default"] = action_name in default_actions

            logger.info(f"Action {action_name} 检查完成: 存在={result['exists']}, 默认={result['is_default']}")

        except Exception as e:
            logger.error(f"检查Action {action_name} 失败: {e}")
            result["error"] = str(e)

        return result

    def attempt_fix_missing_actions(self) -> Dict[str, Any]:
        """尝试修复缺失的Action"""
        logger.info("尝试修复缺失的Action组件...")

        result = {"fixed_actions": [], "still_missing": [], "errors": []}

        try:
            # 重新加载插件
            plugin_manager.load_all_plugins()

            # 再次检查Action注册状态
            registry_check = self.check_action_registry()

            for required_action in self.required_actions:
                if required_action in registry_check["missing_actions"]:
                    try:
                        # 尝试手动注册核心Action
                        if required_action == "no_reply":
                            self._register_no_reply_action()
                            result["fixed_actions"].append(required_action)
                        else:
                            result["still_missing"].append(required_action)
                    except Exception as e:
                        error_msg = f"修复Action {required_action} 失败: {e}"
                        logger.error(error_msg)
                        result["errors"].append(error_msg)
                        result["still_missing"].append(required_action)

            logger.info(f"Action修复完成: 已修复={result['fixed_actions']}, 仍缺失={result['still_missing']}")

        except Exception as e:
            error_msg = f"Action修复过程失败: {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)

        return result

    def _register_no_reply_action(self):
        """手动注册no_reply Action"""
        try:
            from src.plugins.built_in.core_actions.no_reply import NoReplyAction
            from src.plugin_system.base.component_types import ActionInfo

            # 创建Action信息
            action_info = ActionInfo(
                name="no_reply", description="暂时不回复消息", plugin_name="built_in.core_actions", version="1.0.0"
            )

            # 注册Action
            success = component_registry._register_action_component(action_info, NoReplyAction)
            if success:
                logger.info("手动注册no_reply Action成功")
            else:
                raise Exception("注册失败")

        except Exception as e:
            raise Exception(f"手动注册no_reply Action失败: {e}") from e

    def run_full_diagnosis(self) -> Dict[str, Any]:
        """运行完整诊断"""
        logger.info("🔧 开始Action组件完整诊断")
        logger.info("=" * 60)

        diagnosis_result = {
            "plugin_status": {},
            "registry_status": {},
            "action_details": {},
            "fix_attempts": {},
            "summary": {},
        }

        # 1. 检查插件加载
        logger.info("\n📦 步骤1: 检查插件加载状态")
        diagnosis_result["plugin_status"] = self.check_plugin_loading()

        # 2. 检查Action注册
        logger.info("\n📋 步骤2: 检查Action注册状态")
        diagnosis_result["registry_status"] = self.check_action_registry()

        # 3. 检查特定Action详细信息
        logger.info("\n🔍 步骤3: 检查特定Action详细信息")
        diagnosis_result["action_details"] = {}
        for action in self.required_actions:
            diagnosis_result["action_details"][action] = self.check_specific_action(action)

        # 4. 尝试修复缺失的Action
        if diagnosis_result["registry_status"].get("missing_actions"):
            logger.info("\n🔧 步骤4: 尝试修复缺失的Action")
            diagnosis_result["fix_attempts"] = self.attempt_fix_missing_actions()

        # 5. 生成诊断摘要
        logger.info("\n📊 步骤5: 生成诊断摘要")
        diagnosis_result["summary"] = self._generate_summary(diagnosis_result)

        self._print_diagnosis_results(diagnosis_result)

        return diagnosis_result

    def _generate_summary(self, diagnosis_result: Dict[str, Any]) -> Dict[str, Any]:
        """生成诊断摘要"""
        summary = {"overall_status": "unknown", "critical_issues": [], "recommendations": []}

        try:
            # 检查插件加载状态
            if not diagnosis_result["plugin_status"].get("plugins_loaded"):
                summary["critical_issues"].append("插件加载失败")
                summary["recommendations"].append("检查插件系统配置")

            # 检查必需Action
            missing_actions = diagnosis_result["registry_status"].get("missing_actions", [])
            if "no_reply" in missing_actions:
                summary["critical_issues"].append("缺失no_reply Action")
                summary["recommendations"].append("检查core_actions插件是否正确加载")

            # 检查修复结果
            if diagnosis_result.get("fix_attempts"):
                still_missing = diagnosis_result["fix_attempts"].get("still_missing", [])
                if still_missing:
                    summary["critical_issues"].append(f"修复后仍缺失Action: {still_missing}")
                    summary["recommendations"].append("需要手动修复插件注册问题")

            # 确定整体状态
            if not summary["critical_issues"]:
                summary["overall_status"] = "healthy"
            elif len(summary["critical_issues"]) <= 2:
                summary["overall_status"] = "warning"
            else:
                summary["overall_status"] = "critical"

        except Exception as e:
            summary["critical_issues"].append(f"摘要生成失败: {e}")
            summary["overall_status"] = "error"

        return summary

    def _print_diagnosis_results(self, diagnosis_result: Dict[str, Any]):
        """打印诊断结果"""
        logger.info("\n" + "=" * 60)
        logger.info("📈 诊断结果摘要")
        logger.info("=" * 60)

        summary = diagnosis_result.get("summary", {})
        overall_status = summary.get("overall_status", "unknown")

        # 状态指示器
        status_indicators = {
            "healthy": "✅ 系统健康",
            "warning": "⚠️ 存在警告",
            "critical": "❌ 存在严重问题",
            "error": "💥 诊断出错",
            "unknown": "❓ 状态未知",
        }

        logger.info(f"🎯 整体状态: {status_indicators.get(overall_status, overall_status)}")

        # 关键问题
        critical_issues = summary.get("critical_issues", [])
        if critical_issues:
            logger.info("\n🚨 关键问题:")
            for issue in critical_issues:
                logger.info(f"   • {issue}")

        # 建议
        recommendations = summary.get("recommendations", [])
        if recommendations:
            logger.info("\n💡 建议:")
            for rec in recommendations:
                logger.info(f"   • {rec}")

        # 详细状态
        plugin_status = diagnosis_result.get("plugin_status", {})
        if plugin_status.get("plugins_loaded"):
            logger.info(f"\n📦 插件状态: 已加载 {plugin_status.get('total_plugins', 0)} 个插件")
        else:
            logger.info("\n📦 插件状态: ❌ 插件加载失败")

        registry_status = diagnosis_result.get("registry_status", {})
        total_actions = registry_status.get("total_actions", 0)
        missing_actions = registry_status.get("missing_actions", [])
        logger.info(f"📋 Action状态: 已注册 {total_actions} 个，缺失 {len(missing_actions)} 个")

        if missing_actions:
            logger.info(f"   缺失的Action: {missing_actions}")

        logger.info("\n" + "=" * 60)


def main():
    """主函数"""
    diagnostics = ActionDiagnostics()

    try:
        result = diagnostics.run_full_diagnosis()

        # 保存诊断结果
        import orjson

        with open("action_diagnosis_results.json", "w", encoding="utf-8") as f:
            f.write(orjson.dumps(result, option=orjson.OPT_INDENT_2).decode("utf-8"))

        logger.info("📄 诊断结果已保存到: action_diagnosis_results.json")

        # 根据诊断结果返回适当的退出代码
        summary = result.get("summary", {})
        overall_status = summary.get("overall_status", "unknown")

        if overall_status == "healthy":
            return 0
        elif overall_status == "warning":
            return 1
        else:
            return 2

    except KeyboardInterrupt:
        logger.info("❌ 诊断被用户中断")
        return 3
    except Exception as e:
        logger.error(f"❌ 诊断执行失败: {e}")
        import traceback

        traceback.print_exc()
        return 4


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)

    exit_code = main()
    sys.exit(exit_code)
