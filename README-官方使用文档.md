# MediaCrawler 官方使用文档

> 版本 1.4.2 | 本地 WebUI 操作版

---

## 目录

1. [项目概述](#1-项目概述)
2. [环境要求](#2-环境要求)
3. [快速开始](#3-快速开始)
4. [配置说明](#4-配置说明)
5. [Dashboard 使用指南](#5-dashboard-使用指南)
6. [本机采集流程](#6-本机采集流程)
7. [数据存储与导出](#7-数据存储与导出)
8. [飞书 Webhook 通知](#8-飞书-webhook-通知)
9. [常见问题](#9-常见问题)

---

## 1. 项目概述

MediaCrawler 是一个多平台公开内容采集工具，当前 WebUI 以本机直接采集为主，支持查看运行日志、管理导出文件、检查配置、配置 Webhook 和 AI 模型。

| 平台 | 标识 | 支持方式 |
| --- | --- | --- |
| 小红书 | xhs | 关键词、指定ID、创作者 |
| 抖音 | dy | 关键词、指定ID、创作者 |
| 快手 | ks | 关键词、指定ID、创作者 |
| Bilibili | bili | 关键词、指定ID、创作者 |
| 微博 | wb | 关键词、指定ID、创作者 |
| 贴吧 | tieba | 关键词、指定ID、创作者 |
| 知乎 | zhihu | 关键词、指定ID、创作者 |

## 2. 环境要求

- Python 3.11+
- uv
- Node.js 16+（部分平台签名或文档构建场景需要）
- Chrome 浏览器（推荐用于 CDP 模式）

安装依赖：

```powershell
cd E:\codex\GitHub项目\MediaCrawler
uv sync
```

如需标准 Playwright 浏览器模式：

```powershell
uv run playwright install
```

## 3. 快速开始

### 启动 WebUI

推荐直接使用项目根目录的启动脚本：

```powershell
.\启动WebUI.bat
```

也可以手动启动：

```powershell
uv run uvicorn api.main:app --host 0.0.0.0 --port 8081 --reload
```

启动后在浏览器访问：

```text
http://localhost:8081
```

或：

```text
http://127.0.0.1:8081
```

注意：`0.0.0.0` 是服务监听地址，不是浏览器访问地址；不要使用 `http://0.0.0.0:8081` 打开页面。

## 4. 配置说明

### 环境变量

项目会读取根目录 `.env`。常用变量如下：

| 变量 | 说明 | 使用场景 |
| --- | --- | --- |
| FEISHU_WEBHOOK_URL | 飞书群机器人 Webhook | 采集完成通知 |
| LLM_API_KEY | AI 模型 API Key | AI 模型配置 |
| LLM_API_URL | AI 模型接口地址 | AI 模型配置 |
| LLM_MODEL | AI 模型名称 | AI 模型配置 |

### Chrome CDP 模式

如需复用已有 Chrome 登录状态，请开启 Chrome 远程调试。确认 `localhost:9222` 可访问后再启动采集。

如果不使用 CDP，可在配置中切换为标准 Playwright 模式。

## 5. Dashboard 使用指南

左侧导航当前包含：

- 总览
- 需求库
- 配置检查
- Webhook
- AI 模型

### 总览

总览页包含两个主要区域：

- 本机直接采集：填写采集参数并启动本机采集。
- 运行日志：实时查看控制台和本机采集日志。

页面不会保存 Cookie 或账号信息。采集参数下方的 JSON/命令预览已隐藏，仅保留安全说明文字。

### 需求库

查看本地导出文件，支持：

- 预览数据
- 下载文件
- 对支持的文件执行 Dry-Run
- 生成分析报告

### 配置检查

检查本机环境、飞书配置、支持平台和保存格式状态。

### Webhook

配置飞书群机器人 Webhook。配置完成后可点击测试连接。

### AI 模型

配置用于数据分析的 OpenAI 兼容模型接口，包括 API Key、API URL 和模型名称。

## 6. 本机采集流程

1. 打开 `http://localhost:8081`。
2. 在左侧点击 `总览`。
3. 在 `本机直接采集` 区域选择平台。
4. 选择采集类型：
   - 关键词：填写关键词。
   - 指定ID：填写一个或多个内容 ID。
   - 创作者：填写一个或多个创作者 ID。
5. 选择登录方式、保存格式、起始页、最大内容数。
6. 按需勾选一级评论、二级评论、无头浏览器。
7. 勾选 `我确认仅采集公开内容并遵守平台规则`。
8. 点击 `启动采集`。
9. 在 `运行日志` 区域查看实时状态。

如需停止正在运行的采集，点击 `停止采集`。

## 7. 数据存储与导出

采集数据默认保存在项目根目录的 `data/` 目录。

常见格式：

- JSONL
- CSV
- SQLite
- JSON
- Excel

在 Dashboard 中进入 `需求库` 页面，可查看、预览、下载和分析导出文件。

## 8. 飞书 Webhook 通知

Webhook 用于把采集或分析结果推送到飞书群。

配置步骤：

1. 打开飞书群聊。
2. 进入群设置。
3. 添加自定义机器人。
4. 复制 Webhook URL。
5. 打开 Dashboard 的 `Webhook` 页面。
6. 粘贴 URL 并保存。
7. 点击 `测试连接` 确认可用。

当前版本不再写入飞书表格，推荐使用 Webhook 推送结果。

## 9. 常见问题

### Q1：为什么 `http://0.0.0.0:8081` 打不开？

`0.0.0.0` 是服务监听地址，浏览器应访问：

```text
http://localhost:8081
```

或：

```text
http://127.0.0.1:8081
```

### Q2：如何确认 WebUI 服务正常？

访问健康检查接口：

```text
http://localhost:8081/api/health
```

正常返回：

```json
{"status":"ok"}
```

### Q3：采集时弹出二维码怎么办？

首次采集可能需要扫码登录。请用对应平台 App 扫码，并在登录完成后保持浏览器或会话可用。

### Q4：为什么没有看到采集任务列表？

当前界面已简化为本机直接采集流程，左侧不再单独提供 `采集任务` 和 `运行日志` 入口。请在 `总览` 页完成本机采集并查看运行日志。

### Q5：端口被占用怎么办？

查看 8081 端口占用：

```powershell
Get-NetTCPConnection -LocalPort 8081 -State Listen
```

如需临时换端口：

```powershell
uv run uvicorn api.main:app --host 0.0.0.0 --port 8082 --reload
```

然后访问：

```text
http://localhost:8082
```

### Q6：CDP 端口 9222 不可访问怎么办？

确认 Chrome 已开启远程调试，并检查：

```text
http://localhost:9222/json
```

如果不使用 CDP，请改用标准 Playwright 模式。
