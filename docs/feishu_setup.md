# 飞书多维表格同步配置

## 使用场景

该 MVP 只同步 MediaCrawler 已导出的 JSONL、CSV 或 SQLite 数据，不接入核心爬虫流程，不采集登录墙、私密社群或个人敏感信息。

## 创建飞书自建应用

1. 进入飞书开放平台，创建企业自建应用。
2. 在应用凭证页面获取 `App ID` 和 `App Secret`。
3. 为应用开通多维表格相关权限，并发布应用版本。
4. 将应用添加到目标多维表格所在空间，确保应用有写入记录权限。

环境变量：

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_APP_TOKEN=base_xxx
FEISHU_TABLE_ID=tbl_xxx
FEISHU_TASK_TABLE_ID=tbl_task_xxx
```

不要把这些值写入代码、提交到 Git，或打印到日志。

如果“采集任务表”和“需求库表”不在同一个多维表格应用中，可以额外设置：

```bash
FEISHU_TASK_APP_TOKEN=base_task_xxx
```

不设置时，任务表默认使用 `FEISHU_APP_TOKEN`。

## 获取 app_token 和 table_id

打开目标飞书多维表格，浏览器地址通常包含：

```text
https://xxx.feishu.cn/base/{app_token}?table={table_id}
```

其中：

- `{app_token}` 填入 `FEISHU_APP_TOKEN`
- `{table_id}` 填入 `FEISHU_TABLE_ID`

## 多维表格字段

### 需求库表字段

请在目标表中创建以下字段，字段名必须一致：

| 字段名 | 建议类型 |
| --- | --- |
| 需求标题 | 文本 |
| 来源平台 | 单选或文本 |
| 关键词 | 文本 |
| 原文内容 | 多行文本 |
| 来源链接 | URL 或文本 |
| 发布时间 | 数字、日期或文本 |
| 采集时间 | 数字、日期或文本 |
| 内容哈希 | 文本 |
| 需求类型 | 单选或文本 |
| 优先级 | 单选或文本 |
| 状态 | 单选或文本 |
| 备注 | 多行文本 |

`来源链接` 和 `原文内容` 是证据链字段，请保留。

### 采集任务表字段

表格驱动采集使用另一张表作为任务队列。请创建以下字段：

| 字段名 | 建议类型 | 说明 |
| --- | --- | --- |
| 状态 | 单选或文本 | `待执行`、`运行中`、`已完成`、`部分失败`、`失败` |
| 平台 | 单选或文本 | `xhs`、`dy`、`ks`、`bili`、`wb`、`tieba`、`zhihu` |
| 采集类型 | 单选或文本 | `search`、`detail`、`creator` |
| 关键词 | 文本 | `search` 模式必填，多个关键词用英文逗号分隔 |
| 指定ID | 文本 | `detail` 模式必填，多个 ID 用英文逗号分隔 |
| 创作者ID | 文本 | `creator` 模式必填，多个 ID 用英文逗号分隔 |
| 最大数量 | 数字 | 默认 `15` |
| 一级评论 | 复选框、单选或文本 | 为空默认开启；可填 `是/否` |
| 二级评论 | 复选框、单选或文本 | 为空默认关闭；可填 `是/否` |
| 登录方式 | 单选或文本 | 默认 `qrcode`；支持 `qrcode`、`phone`、`cookie`，但任务表不读取 Cookie |
| 输出文件 | 多行文本 | 脚本回写 |
| 成功条数 | 数字 | 脚本回写 |
| 跳过条数 | 数字 | 脚本回写 |
| 失败条数 | 数字 | 脚本回写 |
| 错误信息 | 多行文本 | 脚本回写 |
| 开始时间 | 文本或日期 | 脚本回写 |
| 完成时间 | 文本或日期 | 脚本回写 |

## 运行示例

dry-run 只统计和打印样例 payload，不请求飞书：

```bash
uv run python scripts/sync_to_feishu.py --input data/example.jsonl --format jsonl --dry-run
```

正式同步 JSONL：

```bash
uv run python scripts/sync_to_feishu.py --input data/example.jsonl --format jsonl --batch-size 100
```

同步 CSV：

```bash
uv run python scripts/sync_to_feishu.py --input data/example.csv --format csv --batch-size 100
```

同步 SQLite：

```bash
uv run python scripts/sync_to_feishu.py --input database/sqlite_tables.db --format sqlite --batch-size 100
```

表格驱动采集，读取采集任务表中 `状态=待执行` 的记录：

```bash
uv run python scripts/run_feishu_tasks.py --limit 1 --dry-run
```

确认 dry-run 输出的 MediaCrawler 命令正确后，正式执行：

```bash
uv run python scripts/run_feishu_tasks.py --limit 1 --timeout 3600
```

脚本会：

1. 读取采集任务表中的 `待执行` 记录。
2. 将任务状态回写为 `运行中`。
3. 调用 MediaCrawler CLI，输出 JSONL 到 `.sync_state/feishu_task_runs/<record_id>/`。
4. 调用 `sync_to_feishu.py` 的同步逻辑写入需求库表。
5. 回写 `已完成/部分失败/失败`、成功条数、跳过条数、失败条数和输出文件。

同步状态保存在：

```text
.sync_state/feishu_synced_hashes.json
```

该文件用于按 `内容哈希` 去重，避免重复写入飞书。

## 官方接口

脚本使用飞书开放平台接口：

- 获取 tenant access token：[tenant_access_token/internal](https://open.feishu.cn/document/server-docs/authentication-management/access-token/tenant_access_token_internal)
- 列出多维表格记录：[records/list](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/list?lang=zh-CN)
- 更新多维表格记录：[records/update](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/update?lang=zh-CN)
- 批量新增多维表格记录：[records/batch_create](https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/batch_create?lang=zh-CN)

单批最多 500 条记录；脚本默认 `--batch-size 100`。
