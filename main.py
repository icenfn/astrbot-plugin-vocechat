"""AstrBot 插件：astrbot_plugin_vocechat

VoceChat 平台适配器插件。将 VoceChat 接入 AstrBot，使其作为一个消息平台使用：
- 在 AstrBot「配置 → 消息平台适配器」中添加 VoceChat 连接
- 支持多个 VoceChat 机器人实例（每个实例独立配置 server_url / api_key / webhook）
- 通过 Webhook 接收 VoceChat 消息，通过 Bot API 发送回复

参考：
- AstrBot 平台适配器开发：https://docs.astrbot.app/en/dev/plugin-platform-adapter.html
- VoceChat Bot API：https://doc.voce.chat/zh-cn/bot/bot-and-webhook
"""

from __future__ import annotations

from astrbot import logger
from astrbot.api.star import Context, Star, register


@register(
    "astrbot_plugin_vocechat",
    "astrbot-plugin-contrib",
    "VoceChat 平台适配器：将 VoceChat 接入 AstrBot 作为消息平台",
    "1.0.1",
    "https://github.com/icenfn/astrbot-plugin-vocechat",
)
class VoceChatPlugin(Star):
    """插件入口：加载 VoceChat 平台适配器模块。"""

    def __init__(self, context: Context):
        super().__init__(context)
        # 导入即注册适配器（装饰器自动完成注册）
        from . import vocechat_platform_adapter  # noqa: F401

        logger.info("[VoceChat] 平台适配器已加载，可在「配置 → 消息平台适配器」中添加 VoceChat 连接。")
