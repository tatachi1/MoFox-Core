from fastapi import APIRouter
from src.plugin_system.apis import message_api

router = APIRouter()

@router.get("/messages/recent")
async def get_recent_messages(chat_id: str, limit: int = 10):
    """
    获取最近的聊天记录
    """
    # 假设 message_api.get_recent_messages 是一个异步函数
    messages = await message_api.get_recent_messages(chat_id=chat_id, limit=limit)
    return {"chat_id": chat_id, "messages": messages}