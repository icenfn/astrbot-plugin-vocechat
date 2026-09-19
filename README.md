# astrbot-plugin-vocechat

[AstrBot](https://docs.astrbot.app) **VoceChat 平台适配器**插件。将自托管的 [VoceChat](https://doc.voce.chat) 接入 AstrBot，作为一个消息平台使用。

> 适配 AstrBot **v4.16 ~ v4.28.1+**（要求 `>=4.16,<5`）。

## 这是什么

和 QQ、Telegram、微信等平台一样，VoceChat 作为一个消息平台接入 AstrBot：

- 在 AstrBot **「配置 → 消息平台适配器」** 中添加 VoceChat 连接
- 支持**添加多个 VoceChat 机器人实例**（每个连接独立配置）
- 通过 **Webhook** 接收 VoceChat 推送的消息
- 通过 **Bot API** 将 AstrBot 的回复发回 VoceChat

## 架构说明

```
VoceChat Server  ──POST Webhook──▶  AstrBot (本插件)  ──▶  AstrBot 消息处理管线
     ▲                                                              │
     └──────────── Bot API (send_to_user / send_to_group) ◀─────────┘
```

- **接收**：本插件启动一个 HTTP Webhook 服务器，VoceChat 把消息推送到此地址
- **发送**：AstrBot 回复时，本插件通过 VoceChat Bot API 发消息给用户或频道

## 安装

### 方式一：插件市场

在 AstrBot WebUI **插件市场** 搜索 `vocechat` 安装。

### 方式二：手动安装

```bash
cd AstrBot/data/plugins
git clone https://github.com/icenfn/astrbot-plugin-vocechat astrbot_plugin_vocechat
```

然后在 WebUI **重载插件**。

## 配置

安装后，进入 **「配置 → 消息平台适配器」**，点击 `+` 选择 **VoceChat**，填写：

| 配置项 | 说明 |
| --- | --- |
| server_url | VoceChat 服务器地址，如 `https://chat.example.com`（不带末尾斜杠） |
| api_key | 机器人 API Key |
| webhook_host | Webhook 监听地址，默认 `0.0.0.0` |
| webhook_port | Webhook 监听端口，默认 `9300` |
| webhook_path | Webhook 路径，默认 `/vocechat/webhook` |

> 可以添加多个 VoceChat 连接，每个连接使用不同的端口（或同端口不同路径）。

## 在 VoceChat 后台设置 Webhook

1. 在 VoceChat 管理后台进入 **设置 → 机器人&Webhook**。
2. 创建机器人，新增 API Key，填入上面的 `api_key`。
3. 将该机器人的 **Webhook URL** 设置为：
   ```
   http://<你的AstrBot服务器IP>:<webhook_port><webhook_path>
   ```
   例如：`http://192.168.1.10:9300/vocechat/webhook`
4. VoceChat 会自动发 GET 请求校验，返回 200 即通过。

> 注意：VoceChat 服务器需要能访问到 AstrBot 所在的地址。如果两者不在同一内网，需要确保端口可外网访问，或使用内网穿透。

## 支持的消息类型

| VoceChat 消息 | 转换为 AstrBot | 方向 |
| --- | --- | --- |
| 纯文本（text/plain） | Plain | 接收 |
| Markdown（text/markdown） | Plain | 接收 |
| 图片文件（vocechat/file, image/*） | Image | 接收 |
| 其他文件 | Plain 提示 | 接收 |
| AstrBot 文本回复 | 纯文本发送 | 发送 |
| AstrBot 图片回复 | 文件消息（见下方说明） | 发送 |

## 文件结构

```
astrbot_plugin_vocechat/
├── metadata.yaml                  # 插件元数据
├── main.py                        # 插件入口（加载适配器）
├── vocechat_platform_adapter.py  # 平台适配器核心（Webhook + Bot API）
├── vocechat_platform_event.py    # 平台事件（回复发送）
├── requirements.txt               # aiohttp 依赖
└── README.md
```

## 实现说明

- 使用 `aiohttp` 同时启动 Webhook 接收服务器和 Bot API 发送客户端。
- Webhook GET 预校验返回 200；POST 推送处理后返回 200（避免重复推送）。
- 自动识别私聊（`target.uid`）和频道消息（`target.gid`）。
- 忽略编辑/删除等 `reaction` 类型消息。
- 适配器停用时自动关闭 HTTP 服务器和客户端会话。

## 参考

- [AstrBot 平台适配器开发](https://docs.astrbot.app/en/dev/plugin-platform-adapter.html)
- [VoceChat 机器人与 Webhook](https://doc.voce.chat/zh-cn/bot/bot-and-webhook)
- [VoceChat API 文档](https://doc.voce.chat/api)

## License

MIT
