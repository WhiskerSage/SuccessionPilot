# SuccessionPilot 自动找继任系统

## 版本信息
- 项目版本：`0.2.0`
- Python：`>=3.9`
- Node.js：`>=18`
- XHS MCP（vendor）：`0.8.8-local`

## 执行目录与路径约定
- 下文所有命令默认在项目根目录执行（即包含 `README.md`、`config/`、`scripts/` 的目录）。
- 建议先进入项目根目录再执行命令。
```powershell
cd <项目根目录>
```
- 关键目录说明。
- `config/`：配置模板与主配置
- `scripts/`：一键脚本（初始化、登录、守护、Dashboard）
- `src/`：Python 核心代码
- `web/`：前端页面（Dashboard）
- `data/`：运行输出（Excel、CSV、状态、运行快照）
- `logs/`：运行日志
- `vendor/xhs-mcp/`：项目内置 XHS MCP 运行文件


## 一键配置（首次部署，推荐）
1. 初始化环境（自动创建 `.venv`、安装依赖、生成 `.env` 与 `config/config.yaml`）。
```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

2. 填写 `.env`（至少配置邮箱；如需 LLM 再配置 `OPENAI_API_KEY`）。
```env
EMAIL_SMTP_USERNAME=your_name@126.com
EMAIL_SMTP_PASSWORD=your_126_smtp_auth_code
EMAIL_FROM=your_name@126.com
EMAIL_TO=receiver1@example.com,receiver2@example.com
OPENAI_API_KEY=

# 可选：无法自动识别浏览器时填写
CHROME_PATH=

# 可选：仅在 puppeteer require 异常时填写
XHS_PUPPETEER_REQUIRE=
```

3. 扫码登录并检查状态。
```powershell
powershell -ExecutionPolicy Bypass -File scripts/xhs_login.ps1 -Timeout 180
powershell -ExecutionPolicy Bypass -File scripts/xhs_status.ps1
```

4. 单次验收（抓取、过滤、写表、按策略发送）。
```powershell
.\.venv\Scripts\python.exe -m auto_successor.main --config config/config.yaml --run-once
```

5. 启动定时守护运行。
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_auto.ps1 -ConfigPath config/config.yaml
```

6. 可选：直接发送本地已存最新 5 条摘要（不触发抓取）。
```powershell
.\.venv\Scripts\python.exe -m auto_successor.main --config config/config.yaml --send-latest 5
```

## 完整配置清单（按顺序）
### 第 1 步：准备基础环境
- 在项目根目录执行 `scripts/bootstrap.ps1`。
- 预期结果。
- 生成 `.venv/`、`.env`、`config/config.yaml`
- 可执行 `.\.venv\Scripts\python.exe`

### 第 2 步：配置 `.env`（密钥与账号）
至少填写以下字段（仅邮箱模式）。
```env
EMAIL_SMTP_USERNAME=your_name@126.com
EMAIL_SMTP_PASSWORD=your_126_smtp_auth_code
EMAIL_FROM=your_name@126.com
EMAIL_TO=receiver1@example.com,receiver2@example.com
```

按需填写（可选）。
```env
# 微信服务号
WECHAT_SERVICE_APP_ID=
WECHAT_SERVICE_APP_SECRET=
WECHAT_SERVICE_OPENIDS=openid1,openid2

# LLM
OPENAI_API_KEY=

# 浏览器与 Puppeteer 兼容参数
CHROME_PATH=
XHS_PUPPETEER_REQUIRE=
```

### 第 3 步：配置 `config/config.yaml`（主开关）
最小可用（邮箱摘要）建议如下。
```yaml
xhs:
  keyword: "继任"
  search_sort: "time_descending"

email:
  enabled: true
  smtp_host: "smtp.126.com"
  smtp_port: 465
  use_ssl: true

wechat_service:
  enabled: false

llm:
  enabled: false

notification:
  mode: "digest"
  digest_interval_minutes: 30
  digest_min_new_notes: 1
  digest_send_when_no_new: false
  digest_channels: ["email"]
  attach_excel: false
  attach_jobs_csv: false
```

如果你要“邮箱 + 微信服务号”，改这两处。
- `wechat_service.enabled: true`
- `notification.digest_channels: ["email", "wechat_service"]`

如果你要启用 LLM 增强（过滤/岗位抽取/摘要）。
- `.env` 填 `OPENAI_API_KEY`
- `config/config.yaml` 设 `llm.enabled: true`

### 第 4 步：小红书登录（必须）
```powershell
powershell -ExecutionPolicy Bypass -File scripts/xhs_login.ps1 -Timeout 180
powershell -ExecutionPolicy Bypass -File scripts/xhs_status.ps1
```
`status` 里应看到 `loggedIn=true`。

### 第 5 步：单次验收（先跑一轮）
```powershell
.\.venv\Scripts\python.exe -m auto_successor.main --config config/config.yaml --run-once
```
验收点。
- `data/output.xlsx` 已更新
- `data/jobs.csv` 已生成或更新
- `data/state.json` 已写入
- `logs/app.log` 有本轮日志
- 满足摘要条件时收到邮件/微信；无新增默认不发送

### 第 6 步：启动定时任务
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_auto.ps1 -ConfigPath config/config.yaml
```

### 第 7 步：查看前端 Dashboard
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_dashboard.ps1 -Engine auto -BindHost 127.0.0.1 -Port 8787
```
浏览器打开 `http://127.0.0.1:8787`。
如需启用 FastAPI 引擎，可先执行：`pip install -e .[dashboard]`。

### 第 8 步：常用运维命令
手动发送已存最新 5 条摘要（不抓取）。
```powershell
.\.venv\Scripts\python.exe -m auto_successor.main --config config/config.yaml --send-latest 5
```

检查当前小红书登录状态。
```powershell
powershell -ExecutionPolicy Bypass -File scripts/xhs_status.ps1
```

## 项目简介
`SuccessionPilot` 用于持续采集小红书“继任”相关帖子，进行智能过滤与结构化提取，维护本地数据表，并按通知策略发送摘要。

系统目标。
- 自动采集并增量入库
- 过滤非岗位类帖子
- 生成岗位结构化字段与详细摘要
- 支持邮件与微信服务号推送
- 提供浏览器 Dashboard 实时查看数据

## 功能总览
- 采集层：调用 XHS MCP CLI，支持扫码登录、关键词检索、按时间排序、帖子详情抓取
- 智能层：支持 `auto` 与 `agent` 两种模式，按策略执行过滤、岗位抽取、摘要生成
- 存储层：维护 `output.xlsx` 与 `jobs.csv`，并记录运行快照与状态
- 通知层：支持 `digest`、`realtime`、`off` 三种通知模式
- 展示层：内置 Dashboard（办公风格页面）展示线索、摘要、岗位、运行记录

## 目录结构
- `src/auto_successor/`：核心运行逻辑
- `config/config.yaml`：主配置文件
- `.env`：密钥与账号环境变量
- `scripts/`：运行脚本与 XHS 辅助脚本
- `web/`：Dashboard 前端页面
- `data/`：本地数据、状态、运行快照

## 快速定位（文件在哪）
- 主配置文件：`config/config.yaml`
- 配置模板：`config/config.example.yaml`
- 环境变量模板：`.env.example`
- 本地环境变量：`.env`
- 前端主页：`web/index.html`
- 前端脚本：`web/app.js`
- 前端样式：`web/styles.css`
- 自动运行脚本：`scripts/start_auto.ps1`
- Dashboard 脚本：`scripts/start_dashboard.ps1`
- XHS 登录脚本：`scripts/xhs_login.ps1`
- XHS 状态脚本：`scripts/xhs_status.ps1`
- 一键初始化脚本：`scripts/bootstrap.ps1`
- 主数据文件（运行后生成）：`data/output.xlsx`
- 岗位 CSV（运行后生成）：`data/jobs.csv`
- 状态文件（运行后生成）：`data/state.json`
- 运行快照目录：`data/runs/`
- 运行日志：`logs/app.log`

## 环境要求
- Python 3.9 及以上
- Node.js 18 及以上
- Google Chrome（用于 XHS MCP 登录与抓取）
- Windows PowerShell（示例命令按 Windows 编写）

## 手动安装（可选）
```powershell
cd <你的项目目录>
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item config/config.example.yaml config/config.yaml
Copy-Item .env.example .env
```

## 命令行使用
若已激活虚拟环境（`.venv\Scripts\Activate.ps1`），可直接使用。
- `succession-pilot`
- `succession-pilot-dashboard`

若未激活虚拟环境，建议使用。
- `.\.venv\Scripts\python.exe -m auto_successor.main`
- `.\.venv\Scripts\python.exe -m auto_successor.dashboard`

`succession-pilot` 参数。
- `--config`：配置文件路径，默认 `config/config.yaml`
- `--run-once`：只执行一轮后退出
- `--daemon`：循环运行
- `--mode auto|agent|smart`：运行模式，`smart` 会等价映射为 `agent`
- `--interval-minutes N`：覆盖循环间隔
- `--send-latest [N]`：直接发送本地已存最新摘要，默认 `5`

运行行为说明。
- 未指定 `--run-once` 时，程序默认进入循环模式。
- `--send-latest` 不触发抓取，仅从 `succession_summary` 读取已存摘要并发送。
- `--send-latest` 使用 `notification.digest_channels` 作为发送通道。
- `--send-latest` 发送成功后会更新摘要发送时间戳状态（用于下一次 `digest` 计时）。

Dashboard 启动。
```powershell
.\.venv\Scripts\python.exe -m auto_successor.dashboard --engine auto --host 127.0.0.1 --port 8787
```

或使用模块入口。
```powershell
succession-pilot-dashboard --engine auto --host 127.0.0.1 --port 8787
```

或使用脚本。
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_dashboard.ps1 -Engine auto
```

指定地址与端口示例。
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_dashboard.ps1 -Engine auto -BindHost 127.0.0.1 -Port 8787
```

守护运行快捷脚本。
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_auto.ps1 -ConfigPath config/config.yaml
```

## 配置说明
主配置文件：`config/config.yaml`

环境变量文件：`.env`
- 程序启动时会自动读取根目录 `.env`。
- 若某环境变量在系统中已存在，则 `.env` 不会覆盖该变量。

### app
- `timezone`：时区，例如 `Asia/Shanghai`
- `log_level`：日志级别
- `interval_minutes`：循环模式间隔分钟数

### xhs
- `command`：执行命令，通常为 `node`
- `args`：XHS MCP 主脚本路径
- `browser_path`：Chrome 可执行文件路径
- `search_sort`：搜索排序策略
- `keyword`：搜索关键词，建议固定为 `继任`
- `max_results`：每轮最大抓取数量
- `max_detail_fetch`：每轮详情抓取上限
- `login_timeout_seconds`：扫码登录超时
- `command_timeout_seconds`：单次命令超时

### llm
- `enabled`：是否启用 LLM
- `provider`：当前实现为 OpenAI 兼容接口
- `model`：模型名
- `api_key`：可直接写入密钥（不推荐）
- `api_key_env`：环境变量名；兼容直接写入密钥字符串
- `base_url`：兼容接口地址
- `timeout_seconds` `max_tokens` `temperature`：请求参数
- `enabled_for_filter`：是否用于帖子过滤
- `enabled_for_jobs`：是否用于岗位抽取
- `enabled_for_summary`：是否用于摘要增强
- `max_filter_items` `max_job_items` `max_summary_items`：每轮 LLM 处理上限
- `filter_threshold`：过滤阈值
- `strict_filter`：严格过滤开关

### notification
- `mode`：`digest` | `realtime` | `off`
- `digest_interval_minutes`：摘要发送窗口
- `digest_min_new_notes`：触发摘要所需最少新增数
- `digest_send_when_no_new`：无新增是否仍发送
- `digest_top_summaries`：摘要正文最多包含条数
- `digest_channels`：摘要发送通道
- `realtime_channels`：实时发送通道
- `attach_excel`：是否附带 `output.xlsx`（默认关闭）
- `attach_jobs_csv`：是否附带 `jobs.csv`（默认关闭）

当前项目 `config/config.example.yaml` 默认值。
- `xhs.search_sort: time_descending`
- `notification.mode: digest`
- `notification.digest_interval_minutes: 30`
- `notification.digest_send_when_no_new: false`
- `notification.attach_excel: false`
- `notification.attach_jobs_csv: false`

### agent
- `runtime_name`：运行时名称
- `mode`：默认模式（`auto` 或 `agent`）
- `agent_full_detail_fetch`：`agent` 模式是否全量抓详情
- `agent_send_top_n`：`agent` 模式发送 Top N
- `agent_include_jd_full`：`agent` 模式摘要是否尽量保留完整 JD
- `global_memory_path` `main_memory_path`：系统提示词文件
- `memory_max_chars`：提示词加载上限
- `smart_*`：历史兼容字段，会自动映射到 `agent_*`

### storage
- `excel_path`：Excel 主数据文件
- `jobs_csv_path`：岗位 CSV 导出路径
- `state_path`：状态文件路径

### email
- `enabled`：是否启用邮件
- `smtp_host` `smtp_port` `use_ssl`：SMTP 连接参数
- `username_env` `password_env` `from_env` `to_env`：环境变量名

### wechat_service
- `enabled`：是否启用微信服务号
- `app_id_env` `app_secret_env` `openids_env`：环境变量名

## .env 配置示例
```env
EMAIL_SMTP_USERNAME=your_name@126.com
EMAIL_SMTP_PASSWORD=your_126_smtp_auth_code
EMAIL_FROM=your_name@126.com
EMAIL_TO=receiver1@example.com,receiver2@example.com

WECHAT_SERVICE_APP_ID=
WECHAT_SERVICE_APP_SECRET=
WECHAT_SERVICE_OPENIDS=openid1,openid2

OPENAI_API_KEY=

CHROME_PATH=
XHS_PUPPETEER_REQUIRE=
```

## XHS MCP 配置
XHS MCP 地址：`https://xhs-mcp.aicu.icu/`

### 1. 路径与依赖
默认使用项目内 `vendor/xhs-mcp`。

说明。
- 如果仓库已包含 `vendor/xhs-mcp`，通常无需再单独下载 MCP。
- 仍需本机安装 `Node.js` 与 `Chrome`。
- 首次在新机器运行时，如 `vendor/xhs-mcp/node_modules` 不完整，请在该目录执行一次 `npm install`。
- 如果浏览器路径自动探测失败，可在 `.env` 中设置 `CHROME_PATH`。
- `scripts/xhs_login.ps1` 与 `scripts/xhs_status.ps1` 会自动优先使用 `CHROME_PATH` 或本机 Chrome/Edge 路径，不依赖 Chromium 下载。

初始化 `vendor/xhs-mcp` 依赖示例。
```powershell
cd vendor/xhs-mcp
$env:PUPPETEER_SKIP_DOWNLOAD="true"
$env:PUPPETEER_SKIP_CHROMIUM_DOWNLOAD="true"
npm install --no-fund --no-audit --cache .npm-cache
cd ../..
```

如遇依赖下载网络问题，可在 `vendor/xhs-mcp` 目录临时切换 npm 源后重试。
```powershell
cd vendor/xhs-mcp
npm config set registry https://registry.npmjs.org/
npm install --no-fund --no-audit --cache .npm-cache
cd ../..
```

在 `config/config.yaml` 的 `xhs` 段配置。
```yaml
xhs:
  command: "node"
  args:
    - "vendor/xhs-mcp/dist/xhs-mcp.js"
  browser_path: "C:/Program Files/Google/Chrome/Application/chrome.exe"
  search_sort: "time_descending"
  keyword: "继任"
```

### 2. 登录状态检查
推荐使用脚本。
```powershell
powershell -ExecutionPolicy Bypass -File scripts/xhs_status.ps1
```

指定浏览器路径示例。
```powershell
powershell -ExecutionPolicy Bypass -File scripts/xhs_status.ps1 -BrowserPath "C:/Program Files/Google/Chrome/Application/chrome.exe"
```

或直接执行 MCP 命令。
```powershell
node vendor/xhs-mcp/dist/xhs-mcp.js status --compact
```

### 3. 扫码登录
推荐使用脚本。
```powershell
powershell -ExecutionPolicy Bypass -File scripts/xhs_login.ps1 -Timeout 180
```

指定浏览器路径示例。
```powershell
powershell -ExecutionPolicy Bypass -File scripts/xhs_login.ps1 -Timeout 180 -BrowserPath "C:/Program Files/Google/Chrome/Application/chrome.exe"
```

或直接执行 MCP 命令。
```powershell
node vendor/xhs-mcp/dist/xhs-mcp.js login --timeout 180
```

登录后再次执行 `status`，确认 `loggedIn=true`。

### 4. 排序策略
支持值。
- `general`
- `time_descending`
- `popularity_descending`
- `comment_descending`
- `collect_descending`

兼容别名。
- `latest` `newest` `time` → `time_descending`
- `hot` `likes` → `popularity_descending`
- `comments` → `comment_descending`
- `collects` → `collect_descending`

回退机制。
- 显式排序失败时会自动回退到默认 `search`。
- 详情抓取失败或风控页命中时会保留基础帖子信息，不阻断主流程。
- 详情抓取会复用 MCP 已登录状态。

## 智能处理规则
执行流程。
1. 抓取帖子列表并按发布时间排序。
2. 仅对“状态文件中不存在”的帖子执行增量处理。
3. 过滤非目标帖子。
4. 提取岗位结构化字段。
5. 生成摘要并写入存储。
6. 按通知策略发送。

`auto` 与 `agent` 区别。
- `auto`：按 `llm.max_*` 限额执行，适合稳定低成本运行。
- `agent`：对更多样本做过滤/抽取/摘要，并按 `agent_send_top_n` 发送重点结果。

过滤质量控制。
- 先做规则过滤，再在启用时叠加 LLM 过滤。
- 针对军事、政治等非岗位语境会强制降权或过滤。
- `strict_filter=true` 时采用更保守策略，降低误报。

## 通知策略
### digest（推荐）
触发条件同时满足。
- 到达摘要时间窗口
- 新增数量达到阈值，或 `digest_send_when_no_new=true`

行为。
- 发送聚合摘要
- 可选附带 `output.xlsx` 与 `jobs.csv`（默认关闭）
- 成功发送后写入 `state.json.last_digest_sent_at`
- 默认“无新增不发送”

### realtime
- 每条摘要即时发送到 `realtime_channels`

### off
- 不发送通知，仅本地落盘

## 数据文件与增量规则
### 主数据
- `data/output.xlsx`
- `data/jobs.csv`
- `logs/app.log`

`output.xlsx` 工作表。
- `raw_notes`：原始帖子数据（按 `note_id` 去重更新）
- `succession_summary`：摘要数据（按 `note_id` 去重更新）
- `jobs`：岗位结构化数据（按 `PostID` 去重更新）
- `send_log`：发送日志（追加）

### 状态与快照
- `data/state.json`
- `data/runs/*.json`
- `data/.run.lock`

字段说明。
- `state.json.processed_note_ids`：已处理帖子 ID
- `state.json.last_digest_sent_at`：最近成功摘要发送时间
- `state.json.last_digest_run_id`：最近成功摘要发送所属 run
- `data/runs/*.json`：每轮运行统计、阶段记录、命中 ID、通知结果
- `data/.run.lock`：运行锁，防止重叠执行
- `logs/app.log`：滚动日志，默认单文件上限约 2MB，保留 3 个备份

### 文件占用回退
当 `output.xlsx` 被占用且多次重试失败时，会回退写入。
- `data/output.locked-YYYYMMDD-HHMMSS.xlsx`

## Dashboard
访问地址示例。
- `http://127.0.0.1:8787`

前端能力。
- 总量 KPI
- 线索列表检索
- 岗位/摘要/正文详情联动查看
- 最近运行记录
- 30 秒自动刷新汇总

后端 API。
- `GET /api/health`
- `GET /api/summary`
- `GET /api/leads?limit=200&q=关键词`
- `GET /api/runs?limit=20`

## 常见问题
### 1. 无法登录小红书
- 检查 `xhs.browser_path` 是否为本机 Chrome 路径
- 重新执行 `login --timeout 180` 后再 `status --compact`
- 检查网络环境是否触发风控页

### 2. 配置了时间排序但结果未按预期
- 先确认 `xhs.search_sort` 已设置为 `time_descending`
- 若站点策略导致排序请求失败，系统会自动回退默认搜索

### 3. 126 邮箱发送失败
- 必须使用 SMTP 授权码，不可使用邮箱登录密码
- 确认 `EMAIL_SMTP_USERNAME/EMAIL_SMTP_PASSWORD/EMAIL_TO` 已配置
- 确认 `email.enabled=true`、`smtp_host=smtp.126.com`、`smtp_port=465`

### 4. 运行时报“锁存在”
- 说明有上一轮未正常释放
- 确认没有正在运行的进程后，删除 `data/.run.lock`

### 5. 无新增时是否发送邮件
- 在 `digest` 模式下，默认无新增不发送
- 由 `notification.digest_send_when_no_new` 控制

## 测试
```powershell
python -m unittest discover -s tests -v
```

## 许可
项目为本地自用工程，请按实际团队规范管理代码与密钥。


## Dashboard 引擎切换（框架化）

现在 Dashboard 支持三种引擎：
- `auto`：优先 FastAPI（若未安装则自动回退 legacy）
- `fastapi`：强制 FastAPI
- `legacy`：原生内置 HTTP 服务

### 启动方式
```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_dashboard.ps1 -Engine auto
powershell -ExecutionPolicy Bypass -File scripts/start_dashboard.ps1 -Engine fastapi
powershell -ExecutionPolicy Bypass -File scripts/start_dashboard.ps1 -Engine legacy
```

### 安装 FastAPI 引擎依赖（可选）
```powershell
pip install -e .[dashboard]
```

说明：未安装 FastAPI 时，`-Engine auto` 会自动回退到 legacy，不影响使用。

## Dashboard 多页面与分页

- 页面入口：
  - `http://127.0.0.1:8787/index.html`（总览）
  - `http://127.0.0.1:8787/control.html`（控制中心）
  - `http://127.0.0.1:8787/leads.html`（线索中心）
  - `http://127.0.0.1:8787/summary.html`（摘要中心）
- 线索列表默认分页加载，不再一次性展示全部数据。
- 分页 API：`GET /api/leads?limit=30&page=1&view=all&q=关键词`
  - `view=summary` 表示只返回有摘要的线索。
  - 响应字段包含：`items`、`total`、`page`、`page_size`、`total_pages`。
## 版本更新记录

| 版本 | 日期 | 更新内容 |
|---|---|---|
| v0.2.0 | 2026-02-25 | Dashboard 框架化（auto/fastapi/legacy 引擎切换）；前端拆分多页面（总览/控制中心/线索中心/摘要中心）；线索接口与页面支持分页；控制台功能接入页面。 |
| v0.1.0 | 2026-02-24 | 项目首版：小红书采集、LLM 过滤与摘要、结构化岗位提取、本地 Excel/CSV 落盘、邮件/微信通知、基础 Dashboard。 |

