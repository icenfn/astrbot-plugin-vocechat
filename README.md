# astrbot-plugin-vocechat

将自托管的 [VoceChat](https://doc.voce.chat) 接入 [AstrBot](https://docs.astrbot.app)，作为一个消息平台使用。

---

## 功能特性

- 在 AstrBot **「配置 → 消息平台适配器」** 中直接添加 VoceChat 连接
- 支持**多机器人实例**：每个连接独立配置 `server_url` / `api_key` / Webhook
- 通过 **Webhook** 接收 VoceChat 推送的消息，通过 **Bot API** 发送回复
- 自动区分**私聊**与**频道群聊**消息
- 支持文本、Markdown、图片、文件消息的收发
- 适配器启停时自动管理 HTTP 服务器与客户端会话

## 工作原理

```
VoceChat Server  ──POST Webhook──▶  AstrBot (本插件)  ──▶  AstrBot 消息处理管线
     ▲                                                              │
     └──────────── Bot API（send_to_user / send_to_group）◀─────────┘
```

- **接收**：插件内置一个 aiohttp HTTP 服务器，VoceChat 将消息推送到该地址
- **发送**：AstrBot 回复时，插件调用 VoceChat Bot API 将消息发回用户或频道

## 安装

### 方式一：插件市场

在 AstrBot WebUI 的**插件市场**搜索 `vocechat` 并安装。

### 方式二：手动安装

```bash
cd AstrBot/data/plugins
git clone https://github.com/icenfn/astrbot-plugin-vocechat astrbot_plugin_vocechat
```

安装后在 WebUI 点击**重载插件**。

## 配置

进入 **「配置 → 消息平台适配器」**，点击 `+` 选择 **VoceChat**，填写以下参数：

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `server_url` | string | — | VoceChat 服务器地址，如 `https://chat.example.com`，**不带末尾斜杠** |
| `api_key` | string | — | 在 VoceChat 后台创建机器人后生成的 API Key |
| `webhook_host` | string | `0.0.0.0` | Webhook 监听网卡，`0.0.0.0` 表示监听所有地址 |
| `webhook_port` | int | `9300` | Webhook 监听端口；多实例时每个连接需用不同端口 |
| `webhook_path` | string | `/vocechat/webhook` | Webhook 路径，需与 VoceChat 后台填写的完全一致 |

> 可以添加多个 VoceChat 连接，每个连接使用不同端口（或同端口不同路径）。

## 在 VoceChat 后台配置 Webhook

1. 打开 VoceChat 管理后台，进入 **设置 → 机器人 & Webhook**。
2. 创建一个机器人，点击**新增 API Key**，将其填入插件配置的 `api_key`。
3. 将该机器人的 **Webhook URL** 设置为：
   ```
   http://<AstrBot服务器地址>:<webhook_port><webhook_path>
   ```
   例如：`http://192.168.1.10:9300/vocechat/webhook`
4. VoceChat 会自动发送一个 GET 请求进行校验，插件返回 `200` 即配置成功。

> **网络要求**：VoceChat 服务器必须能访问到 AstrBot 所在地址。若二者不在同一内网，需确保端口对公网可达，或使用内网穿透（如 frp、ngrok）。

## 消息类型支持

| VoceChat 侧 | 转换为 AstrBot | 方向 |
| --- | --- | --- |
| 纯文本（`text/plain`） | Plain | 接收 |
| Markdown（`text/markdown`） | Plain | 接收 |
| 图片文件（`vocechat/file`, `image/*`） | Image | 接收 |
| 其他文件 | Plain 文本提示 | 接收 |
| AstrBot 文本回复 | 纯文本发送 | 发送 |
| AstrBot 图片回复 | 先上传文件再发送 | 发送 |

- 发送图片时，插件会自动走 VoceChat 的文件上传流程（prepare → upload → send）。
- 编辑、删除等 `reaction` 类型的消息会被自动忽略。

## 文件结构

```
astrbot_plugin_vocechat/
├── metadata.yaml               # 插件元数据（名称、版本、依赖等）
├── main.py                     # 插件入口，注册并加载适配器
├── vocechat_platform_adapter.py  # 平台适配器核心：Webhook 接收 + Bot API 发送
├── vocechat_platform_event.py   # 平台事件：将回复消息链发回 VoceChat
├── requirements.txt            # Python 依赖（aiohttp）
├── logo.png                    # 插件图标
└── README.md
```

## 常见问题

**Q：Webhook 校验失败？**
确认 `webhook_host` 没有误填为 `127.0.0.1`（那样只允许本机访问），并检查防火墙/安全组是否放行对应端口。

**Q：消息收得到但回复发不出去？**
检查 `server_url` 是否正确（不带末尾斜杠）、`api_key` 是否有效、VoceChat 服务器是否可达。

**Q：添加多个机器人要怎么配？**
新建第二个 VoceChat 连接，把 `webhook_port` 改成另一个未占用端口即可。

## 开发说明

- 基于 `aiohttp` 同时运行 Webhook 接收服务器和 Bot API 客户端，异步非阻塞。
- Webhook 对 GET 预校验返回 `200`；POST 推送处理后同样返回 `200`，避免 VoceChat 重复投递。
- 私聊会话 ID 格式为 `private_<uid>`，频道消息为 `g<gid>_<uid>`。
- 适配器被停用时自动清理 HTTP 服务器和客户端会话，无残留连接。

## 参考

- [AstrBot 平台适配器开发文档](https://docs.astrbot.app/en/dev/plugin-platform-adapter.html)
- [VoceChat 机器人与 Webhook](https://doc.voce.chat/zh-cn/bot/bot-and-webhook)
- [VoceChat API 文档](https://doc.voce.chat/api)

## License

MIT
