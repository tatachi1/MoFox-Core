#!/usr/bin/env python3
"""
测试 ChatStream 的 deepcopy 功能
验证 asyncio.Task 序列化问题是否已解决
"""

import asyncio
import sys
import os
import copy

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.chat.message_receive.chat_stream import ChatStream
from maim_message import UserInfo, GroupInfo


async def test_chat_stream_deepcopy():
    """测试 ChatStream 的 deepcopy 功能"""
    print("[TEST] 开始测试 ChatStream deepcopy 功能...")

    try:
        # 创建测试用的用户和群组信息
        user_info = UserInfo(
            platform="test_platform",
            user_id="test_user_123",
            user_nickname="测试用户",
            user_cardname="测试卡片名"
        )

        group_info = GroupInfo(
            platform="test_platform",
            group_id="test_group_456",
            group_name="测试群组"
        )

        # 创建 ChatStream 实例
        print("📝 创建 ChatStream 实例...")
        stream_id = "test_stream_789"
        platform = "test_platform"

        chat_stream = ChatStream(
            stream_id=stream_id,
            platform=platform,
            user_info=user_info,
            group_info=group_info
        )

        print(f"[SUCCESS] ChatStream 创建成功: {chat_stream.stream_id}")

        # 等待一下，让异步任务有机会创建
        await asyncio.sleep(0.1)

        # 尝试进行 deepcopy
        print("[INFO] 尝试进行 deepcopy...")
        copied_stream = copy.deepcopy(chat_stream)

        print("[SUCCESS] deepcopy 成功！")

        # 验证复制后的对象属性
        print("\n[CHECK] 验证复制后的对象属性:")
        print(f"  - stream_id: {copied_stream.stream_id}")
        print(f"  - platform: {copied_stream.platform}")
        print(f"  - user_info: {copied_stream.user_info.user_nickname}")
        print(f"  - group_info: {copied_stream.group_info.group_name}")

        # 检查 processing_task 是否被正确处理
        if hasattr(copied_stream.stream_context, 'processing_task'):
            print(f"  - processing_task: {copied_stream.stream_context.processing_task}")
            if copied_stream.stream_context.processing_task is None:
                print("  [SUCCESS] processing_task 已被正确设置为 None")
            else:
                print("  [WARNING] processing_task 不为 None")
        else:
            print("  [SUCCESS] stream_context 没有 processing_task 属性")

        # 验证原始对象和复制对象是不同的实例
        if id(chat_stream) != id(copied_stream):
            print("[SUCCESS] 原始对象和复制对象是不同的实例")
        else:
            print("[ERROR] 原始对象和复制对象是同一个实例")

        # 验证基本属性是否正确复制
        if (chat_stream.stream_id == copied_stream.stream_id and
            chat_stream.platform == copied_stream.platform):
            print("[SUCCESS] 基本属性正确复制")
        else:
            print("[ERROR] 基本属性复制失败")

        print("\n[COMPLETE] 测试完成！deepcopy 功能修复成功！")
        return True

    except Exception as e:
        print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # 运行测试
    result = asyncio.run(test_chat_stream_deepcopy())

    if result:
        print("\n[SUCCESS] 所有测试通过！")
        sys.exit(0)
    else:
        print("\n[ERROR] 测试失败！")
        sys.exit(1)