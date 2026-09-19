"""VoceChat 平台事件。

负责将 AstrBot 的回复消息链通过 Bot API 发回 VoceChat。
"""

from __future__ import annotations

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Image, Plain
from astrbot.api.platform import AstrBotMessage, MessageType, PlatformMetadata


class VoceChatPlatformEvent(AstrMessageEvent):
    """VoceChat 消息事件。"""

    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        adapter,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.adapter = adapter

    async def send(self, message: MessageChain):
        """将 AstrBot 的回复发送回 VoceChat。"""
        abm: AstrBotMessage = self.message_obj

        if abm.type == MessageType.GROUP_MESSAGE:
            target_type = "group"
            target_id = abm.group_id
        else:
            target_type = "user"
            target_id = abm.sender.user_id

        for comp in message.chain:
            if isinstance(comp, Plain):
                if not comp.text:
                    continue
                await self.adapter._send_text(
                    target_type, target_id, comp.text, "text/plain"
                )
            elif isinstance(comp, Image):
                try:
                    img_path = await comp.convert_to_file_path()
                    await self.adapter._send_file(
                        target_type, target_id, img_path
                    )
                except Exception:
                    await self.adapter._send_text(
                        target_type, target_id, "[图片]"
                    )

        await super().send(message)
