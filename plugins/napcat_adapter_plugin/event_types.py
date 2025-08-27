from enum import Enum

class NapcatEvent(Enum):
    # napcat插件事件枚举类 
    ON_RECEIVED_TEXT = "napcat_on_received_text"  # 接收到文本消息
    ON_RECEIVED_FACE = "napcat_on_received_face"  # 接收到表情消息
    ON_RECEIVED_REPLY = "napcat_on_received_reply"  # 接收到回复消息
    ON_RECEIVED_IMAGE = "napcat_on_received_image"  # 接收到图像消息
    ON_RECEIVED_RECORD = "napcat_on_received_record"  # 接收到语音消息
    ON_RECEIVED_VIDEO = "napcat_on_received_video"  # 接收到视频消息
    ON_RECEIVED_AT = "napcat_on_received_at"  # 接收到at消息
    ON_RECEIVED_DICE = "napcat_on_received_dice"  # 接收到骰子消息
    ON_RECEIVED_SHAKE = "napcat_on_received_shake"  # 接收到屏幕抖动消息
    ON_RECEIVED_JSON = "napcat_on_received_json"  # 接收到JSON消息
    ON_RECEIVED_RPS = "napcat_on_received_rps"  # 接收到魔法猜拳消息
    ON_FRIEND_INPUT = "napcat_on_friend_input"  # 好友正在输入
