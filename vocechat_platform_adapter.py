"""VoceChat 平台适配器。

负责：
- 启动 HTTP Webhook 服务器接收 VoceChat 推送的消息
- 将 VoceChat 消息结构转换为 AstrBot 统一消息对象
- 通过 VoceChat Bot API 向用户/频道发送消息
"""

from __future__ import annotations

import asyncio
import mimetypes
import os
from pathlib import Path
from typing import Optional

import aiohttp
from aiohttp import web
from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image, Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core.platform.message_session import MessageSesion

from .vocechat_platform_event import VoceChatPlatformEvent

PLUGIN_ROOT = Path(__file__).resolve().parent

# 每个配置项的可视化提示（description 显示在标签旁，hint 显示在问号 tooltip 中）
CONFIG_METADATA = {
    "server_url": {
        "type": "string",
        "description": "VoceChat 服务器地址",
        "hint": "你的 VoceChat 实例地址，例如 https://chat.example.com ，不要带末尾斜杠。",
    },
    "api_key": {
        "type": "string",
        "description": "Bot API Key",
        "hint": "在 VoceChat 管理后台「设置 → 机器人&Webhook」中创建机器人，点击「新增 API Key」后获取。",
    },
    "webhook_host": {
        "type": "string",
        "description": "Webhook 监听地址",
        "hint": "插件启动的 Webhook HTTP 服务器监听的网卡地址。默认 0.0.0.0 表示监听所有网卡。",
    },
    "webhook_port": {
        "type": "int",
        "description": "Webhook 监听端口",
        "hint": "Webhook 监听端口，默认 9300。添加多个 VoceChat 连接时，每个连接需使用不同端口。",
    },
    "webhook_path": {
        "type": "string",
        "description": "Webhook 接收路径",
        "hint": "Webhook URL 路径，默认 /vocechat/webhook。需与 VoceChat 后台该机器人设置的 Webhook 地址完全一致。",
    },
}


@register_platform_adapter(
    "vocechat",
    "VoceChat",
    logo_path="logo.png",
    default_config_tmpl={
        "server_url": "https://chat.example.com",
        "api_key": "your_bot_api_key",
        "webhook_host": "0.0.0.0",
        "webhook_port": 9300,
        "webhook_path": "/vocechat/webhook",
    },
    config_metadata=CONFIG_METADATA,
)
class VoceChatPlatformAdapter(Platform):
    """VoceChat 平台适配器。"""

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        self.config = platform_config
        self.settings = platform_settings

        self.server_url = str(
            self.config.get("server_url", "")
        ).strip().rstrip("/")
        self.api_key = str(self.config.get("api_key", "")).strip()
        self.webhook_host = str(self.config.get("webhook_host", "0.0.0.0"))
        self.webhook_port = int(self.config.get("webhook_port", 9300))
        self.webhook_path = str(
            self.config.get("webhook_path", "/vocechat/webhook")
        )

        self._runner: Optional[web.AppRunner] = None
        self._http_session: Optional[aiohttp.ClientSession] = None

    # ------------------------------------------------------------------ #
    # Platform 接口
    # ------------------------------------------------------------------ #

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="vocechat",
            description="VoceChat",
            id=str(self.config.get("id", "vocechat")),
        )

    async def run(self):
        """启动 Webhook HTTP 服务器（阻塞运行）。"""
        if not self.server_url or not self.api_key:
            self.record_error(
                "未配置 server_url 或 api_key，适配器无法启动。"
            )
            return

        self._http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15)
        )

        app = web.Application()
        # VoceChat 预校验 Webhook 时会发 GET，必须返回 200
        app.router.add_get(self.webhook_path, self._on_verify)
        app.router.add_post(self.webhook_path, self._on_webhook)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.webhook_host, self.webhook_port)
        await site.start()

        logger.info(
            f"[VoceChat] Webhook 已启动："
            f"http://{self.webhook_host}:{self.webhook_port}{self.webhook_path}"
        )
        logger.info(
            f"[VoceChat] 请在 VoceChat 后台「机器人&Webhook」中将 Webhook 地址设为："
            f"http://<你的AstrBot服务器IP>:{self.webhook_port}{self.webhook_path}"
        )

        try:
            # 阻塞等待，直到任务被取消
            await asyncio.Event().wait()
        finally:
            await self._cleanup()

    async def terminate(self):
        """适配器被停用/卸载时调用。"""
        await self._cleanup()

    async def _cleanup(self):
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            logger.info("[VoceChat] Webhook 服务器已关闭。")
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
            self._http_session = None

    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ):
        """通过会话发送消息。"""
        # session.session_id 格式为 "g<gid>_<uid>" 或 "private_<uid>"
        sid = session.session_id
        if sid.startswith("g"):
            # g<gid>_<uid>
            parts = sid[1:].split("_", 1)
            target_type = "group"
            target_id = parts[0]
        else:
            target_type = "user"
            target_id = sid.replace("private_", "", 1)

        await self._send_chain(target_type, target_id, message_chain)

    # ------------------------------------------------------------------ #
    # Webhook 处理
    # ------------------------------------------------------------------ #

    async def _on_verify(self, request: web.Request) -> web.Response:
        """VoceChat Webhook 预校验（GET），返回 200 即通过。"""
        return web.Response(text="ok", status=200)

    async def _on_webhook(self, request: web.Request) -> web.Response:
        """接收 VoceChat POST 推送的消息。"""
        try:
            data = await request.json()
        except Exception as e:
            logger.warning(f"[VoceChat] Webhook 解析 JSON 失败: {e}")
            return web.Response(text="bad request", status=400)

        try:
            abm = await self.convert_message(data)
            if abm is not None:
                await self.handle_msg(abm)
        except Exception as e:
            logger.error(f"[VoceChat] 处理 Webhook 消息失败: {e}", exc_info=True)

        # 必须返回 200，否则 VoceChat 会重复推送
        return web.Response(text="ok", status=200)

    async def convert_message(self, data: dict) -> Optional[AstrBotMessage]:
        """将 VoceChat 推送的数据转换为 AstrBotMessage。

        返回 None 表示该消息应被忽略（如编辑/删除消息）。
        """
        detail = data.get("detail", {})
        msg_type = detail.get("type", "normal")

        # 只处理普通消息；reaction（编辑/删除）、newuser（新用户注册）等事件忽略
        if msg_type != "normal":
            logger.debug(f"[VoceChat] 忽略非普通消息事件，类型: {msg_type}")
            return None

        content = str(detail.get("content", ""))
        content_type = str(detail.get("content_type", "text/plain"))
        properties = detail.get("properties") or {}
        target = data.get("target", {})
        from_uid = str(data.get("from_uid", ""))
        mid = str(data.get("mid", ""))

        abm = AstrBotMessage()
        abm.message_id = mid
        abm.self_id = str(self.config.get("id", "vocechat_bot"))
        abm.raw_message = data

        # 判断私聊还是频道
        if "gid" in target:
            abm.type = MessageType.GROUP_MESSAGE
            abm.group_id = str(target["gid"])
            abm.session_id = f"g{abm.group_id}_{from_uid}"
        else:
            abm.type = MessageType.FRIEND_MESSAGE
            abm.group_id = ""
            abm.session_id = f"private_{from_uid}"

        abm.sender = MessageMember(
            user_id=from_uid,
            nickname=properties.get("name") or f"用户{from_uid}",
        )

        # 构造消息链
        chain = []
        if content_type == "vocechat/file":
            file_url = (
                f"{self.server_url}/api/resource/file?file_path={content}"
            )
            if str(properties.get("content_type", "")).startswith("image/"):
                chain.append(Image(file=file_url, url=file_url))
                abm.message_str = f"[图片: {properties.get('name', '')}]"
            else:
                chain.append(
                    Plain(text=f"[文件: {properties.get('name', content)}]")
                )
                abm.message_str = chain[-1].text
        else:
            chain.append(Plain(text=content))
            abm.message_str = content

        abm.message = chain
        return abm

    async def handle_msg(self, message: AstrBotMessage):
        """将转换后的消息提交到事件队列。"""
        event = VoceChatPlatformEvent(
            message_str=message.message_str,
            message_obj=message,
            platform_meta=self.meta(),
            session_id=message.session_id,
            adapter=self,
        )
        self.commit_event(event)

    # ------------------------------------------------------------------ #
    # Bot API 发送
    # ------------------------------------------------------------------ #

    async def _send_chain(
        self,
        target_type: str,
        target_id: str,
        message_chain: MessageChain,
    ):
        """将消息链发送到指定目标。"""
        for comp in message_chain.chain:
            if isinstance(comp, Plain):
                await self._send_text(
                    target_type, target_id, comp.text, "text/plain"
                )
            elif isinstance(comp, Image):
                # VoceChat 发送图片需要先上传文件，这里简化为发送文件 URL
                try:
                    img_path = await comp.convert_to_file_path()
                    await self._send_file(
                        target_type, target_id, img_path
                    )
                except Exception as e:
                    logger.warning(f"[VoceChat] 图片发送失败: {e}")
                    await self._send_text(
                        target_type,
                        target_id,
                        f"[图片发送失败: {e}]",
                    )

    async def _send_text(
        self,
        target_type: str,
        target_id: str,
        text: str,
        content_type: str = "text/plain",
    ):
        """通过 Bot API 发送文本/Markdown 消息。"""
        if target_type == "group":
            url = f"{self.server_url}/api/bot/send_to_group/{target_id}"
        else:
            url = f"{self.server_url}/api/bot/send_to_user/{target_id}"

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": content_type,
        }
        try:
            async with self._http_session.post(
                url, headers=headers, data=text
            ) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    logger.warning(
                        f"[VoceChat] 发送消息失败 HTTP {resp.status}: {body}"
                    )
        except Exception as e:
            logger.error(f"[VoceChat] 发送消息异常: {e}")

    async def _send_file(
        self,
        target_type: str,
        target_id: str,
        file_path: str,
    ):
        """上传本地文件并以 vocechat/file 类型发送。

        完整流程（参见 VoceChat FAQ）：
        1. POST /api/bot/file/prepare  → 拿到 file_id
        2. POST /api/bot/file/upload   → 上传文件内容，拿到 path
        3. POST send_to_user/send_to_group，content-type: vocechat/file，
           body: {"path": path}
        """
        try:
            abs_path = os.path.abspath(file_path)
            if not os.path.isfile(abs_path):
                logger.warning(f"[VoceChat] 文件不存在: {abs_path}")
                await self._send_text(
                    target_type, target_id, f"[文件不存在: {file_path}]"
                )
                return

            filename = os.path.basename(abs_path)
            content_type = (
                mimetypes.guess_type(filename)[0] or "application/octet-stream"
            )

            # 第一步：prepare
            prepare_url = f"{self.server_url}/api/bot/file/prepare"
            async with self._http_session.post(
                prepare_url,
                headers={"x-api-key": self.api_key},
                json={"content_type": content_type, "filename": filename},
            ) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    logger.warning(
                        f"[VoceChat] 文件 prepare 失败 HTTP {resp.status}: {body}"
                    )
                    await self._send_text(
                        target_type, target_id, f"[文件上传准备失败: {filename}]"
                    )
                    return
                file_id = (await resp.text()).strip().strip('"')

            # 第二步：upload（一次性上传整个文件）
            upload_url = f"{self.server_url}/api/bot/file/upload"
            with open(abs_path, "rb") as f:
                file_data = f.read()
            form = aiohttp.FormData()
            form.add_field("file_id", file_id)
            form.add_field("chunk_data", file_data, filename=filename)
            form.add_field("chunk_is_last", "true")

            async with self._http_session.post(
                upload_url,
                headers={"x-api-key": self.api_key},
                data=form,
            ) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    logger.warning(
                        f"[VoceChat] 文件 upload 失败 HTTP {resp.status}: {body}"
                    )
                    await self._send_text(
                        target_type, target_id, f"[文件上传失败: {filename}]"
                    )
                    return
                upload_result = await resp.json()
                file_resource_path = upload_result.get("path", "")

            if not file_resource_path:
                logger.warning("[VoceChat] 文件上传未返回 path。")
                await self._send_text(
                    target_type, target_id, f"[文件上传失败: {filename}]"
                )
                return

            # 第三步：以 vocechat/file 类型发送文件消息
            if target_type == "group":
                send_url = (
                    f"{self.server_url}/api/bot/send_to_group/{target_id}"
                )
            else:
                send_url = (
                    f"{self.server_url}/api/bot/send_to_user/{target_id}"
                )
            async with self._http_session.post(
                send_url,
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "vocechat/file",
                },
                json={"path": file_resource_path},
            ) as resp:
                if resp.status not in (200, 201):
                    body = await resp.text()
                    logger.warning(
                        f"[VoceChat] 发送文件消息失败 HTTP {resp.status}: {body}"
                    )
        except Exception as e:
            logger.error(f"[VoceChat] 文件发送异常: {e}", exc_info=True)
            await self._send_text(
                target_type, target_id, f"[文件发送失败: {e}]"
            )