# CubeDeck

现代化 Minecraft 服务器控制台，基于 Python + PySide6。

一套软件管理多台服务器，集成进程控制、RCON 控制台、玩家管理、备份恢复、AI 助手等功能。

---

## 功能

- **服务器管理**：多服务器实例、进程接管、优雅停止
- **控制台**：彩色日志、分类过滤、命令历史
- **玩家管理**：背包编辑、传送、Buff、踢出/封禁/OP
- **权限审计**：细粒度命令授权、越权检测
- **区域管理**：保护区 + 清理区
- **备份恢复**：手动/定时备份、一键恢复
- **服务器属性**：一般 / 专家两种模式
- **AI 助手**：聊天回复、行为审核、上下文感知
- **界面**：6 套主题实时切换

**支持服务端**：Vanilla / Paper / Purpur / Spigot / Forge / NeoForge / Fabric  
**版本要求**：Minecraft 1.16.5+

---

## 安装

```bash
git clone https://github.com/你的用户名/CubeDeck.git
cd CubeDeck

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
python main.py
```

## 快速开始
1.设置 → 填入服务器目录、Java 路径、内存、RCON 端口/密码

2.确保 server.properties 里 enable-rcon=true

3.仪表盘 → 点 启动服务器

首次启动会自动创建 CubeDeck/ 目录保存配置

# 常见问题
## 找不到 Java
设置里指定 java.exe 绝对路径。

## RCON 连接失败
检查端口/密码是否与 server.properties 一致，等服务端完全启动后再连

## 关闭软件会停服务端吗？
不会。服务端继续运行，下次打开自动接管

## AI 助手怎么用？
AI 助手 → API 配置，填入 API 网址、Key、模型名 → 测试连接 → 保存。默认游戏内输入 ! 触发

## 语言文件
不内置。请自行获取zh_cn.json 放到 lang/ 目录

## 许可证
MIT License

本项目不包含、不分发任何 Minecraft 官方资产
