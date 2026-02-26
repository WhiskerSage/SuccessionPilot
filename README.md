# SuccessionPilot 自动找继任系统

## 版本信息
- 项目版本：`0.3.9`
- Python：`>=3.9`
- Node.js：`>=18`
- XHS MCP（vendor）：`0.8.8-local`

### v0.3.9 更新要点
- LLM 超时参数优化：默认 `connect_timeout_seconds=8`、`request_timeout_seconds=20`，兼顾稳定性与速度。
- 套磁文案开关新增：`llm.enabled_for_outreach`（默认 `true`），可按需关闭文案生成以节省调用与耗时。
- 文档与示例配置同步：`README.md` 与 `config/config.example.yaml` 已补充上述参数说明。

### v0.3.8 更新要点
- 提取链路优化为“单次直提”：对每条已补全 `detail_text` 的帖子，优先用一次 LLM 同时完成目标判断（`is_target`）+ 岗位结构化提取（公司/岗位/地点/要求等）。
- 速度优化：默认不再对同一帖子分别做 LLM 筛选和 LLM 岗位提取，减少重复调用。
- 质量兜底：直提失败会回退规则提取；支持开关 `llm.single_pass_extract`（默认 `true`）。

### v0.3.7 更新要点
- 摘要中心视图优化：默认只展示 `发布时间 / 岗位公司 / 岗位要求 / 摘要`，隐藏互动状态、评论预览、原帖正文等噪声字段。
- 摘要详情面板优化：默认聚焦结构化信息（岗位、公司、地点、岗位要求、摘要），更适合复核与发送前检查。
- 前端缓存刷新：页面脚本版本号更新，避免浏览器缓存导致摘要中心仍显示旧布局。

### v0.3.6 更新要点
- 增量写入升级：每轮抓取到的帖子都会写入 `raw_notes`，按 `note_id` 做 upsert，不重复新增行；智能处理仍只针对“新帖子”执行。
- 数据追踪增强：`raw_notes` 新增 `publish_time_quality`、`first_seen_at`、`updated_at` 字段，便于区分首见时间与最近更新时间。
- 时间稳定性优化：发布时间解析失败时保留历史 `publish_timestamp`，避免同一帖子在多轮运行中因回退“当前时间”而排序抖动。
- 前端发布时间统一为绝对时间（`YYYY-MM-DD HH:MM`），避免“分钟前/昨天”等相对时间造成阅读混乱。

### v0.3.5 更新要点
- 新增配置向导：控制中心新增“应用推荐配置 + 标记完成”流程，降低初始配置门槛。
- 新增一键自检：支持对配置文件、数据写入、XHS 依赖、XHS 登录、邮件配置/连接、LLM 配置/连接进行统一检查并给出修复建议。
- 新增自检 API：`GET/POST /api/setup/check`，前端与脚本可复用同一检查能力。

### v0.3.4 更新要点
- Dashboard 皮肤优化：`graphite-office` 升级为明显深色办公主题，表格/按钮/输入框/卡片统一深色化，切换后视觉差异更明确。
- 前端视觉微调：圆角由“偏硬”调整为“适度圆角”，保留办公风的同时提升可读性与整体质感。
- 环境兼容修复：移除脚本与子进程中的 `PYTHONUTF8=1` 强制设置，修复部分 Conda 环境下 `init_import_site`/编码报错问题。

### v0.3.3 更新要点
- 终端中文乱码修复增强：统一设置 UTF-8 运行环境（PowerShell 脚本、Python 日志、Dashboard 子进程），减少运行日志乱码。
- 文本清洗增强：新增“乱码识别 + 回退文本”逻辑，LLM 返回字段若不可读会自动回退到可读规则文本。
- 岗位通知去重优化：`岗位要求` 与 `原文摘要` 不再默认复用同一文本；若高度重合会输出去重提示，避免重复信息。
- LLM 返回 JSON 解码增强：增加 UTF-8/UTF-8-SIG/GB18030 兼容解析，降低上游编码不规范导致的乱码概率。

### v0.3.2 更新要点
- 新增可观测性面板：最近运行记录支持展示阶段总耗时、平均耗时、失败阶段数、慢阶段 Top、错误码分布。
- 运行统计增强：`data/runs/*.json` 的 `stats` 新增阶段耗时与错误码聚合字段，便于回放与排障。
- `/api/runs` 输出增强：统一提供 `stage_total_ms`、`stage_avg_ms`、`stage_failed_count`、`slow_stages`、`error_codes` 字段，并兼容历史快照回退解析。
- LLM 调用策略维持全量模式，并保留降级/恢复日志，便于观察 LLM 可用性波动。
- 邮件通知维持 HTML 办公风模板（无圆角、表格化排版）并保持中文显示兼容优化。


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
1. 初始化环境（自动创建 `.venv`、安装依赖含 dashboard/上传解析相关包、生成 `.env` 与 `config/config.yaml`，并自动创建 `config/resume.txt` 空文件）。
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

resume:
  source_txt_path: "config/resume.txt"
  resume_text_path: "data/resume_text.txt"
  max_chars: 6000
```

简历上下文说明。
- 复制 `config/resume.example.txt` 为 `config/resume.txt`，填写你的真实简历内容（TXT）。
- 运行时由 `resume_loader` 读取并裁剪，写入 `resume_text_path`，供 LLM 在岗位结构化提取、批次摘要与机会点套磁文案复用。
- 已预留后续前端 PDF 上传扩展接口（`resume_loader.update_from_upload_bytes` / `parse_pdf_bytes`）。

如果你要“邮箱 + 微信服务号”，改这两处。
- `wechat_service.enabled: true`
- `notification.digest_channels: ["email", "wechat_service"]`

如果你要启用 LLM 增强（过滤/岗位抽取/摘要）。
- `.env` 填 `OPENAI_API_KEY`
- `config/config.yaml` 设 `llm.enabled: true`
- 建议保持 `llm.single_pass_extract: true`（默认），启用“单次直提”减少重复调用
- 如需拆分“帖子解析模型”和“套磁文案模型”，可在 `llm` 下单独配置：
```yaml
llm:
  enabled: true
  single_pass_extract: true
  request_timeout_seconds: 20
  connect_timeout_seconds: 8
  model: "gpt-5-mini"           # 通用兜底模型
  parse_model: "deepseek-chat"  # 帖子解析/结构化/摘要
  outreach_model: "deepseek-chat" # 套磁文案
  enabled_for_outreach: true
```

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

### 第 8 步：配置向导（推荐）
打开 `http://127.0.0.1:8787/control.html`，按顺序操作。
1. 点击“应用推荐配置”（自动设置关键词、排序、周期等建议值）。
2. 点击“一键自检”（检查配置、写入权限、XHS、邮件、LLM）。
3. 按建议修复后再次自检，直到失败项为 0。
4. 点击“标记向导完成”。

### 第 9 步：常用运维命令
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
- 你的简历：`config/resume.txt`
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
- `model`：默认模型名（兜底）
- `parse_model`：帖子解析/结构化/摘要使用的模型；为空时回退 `model`
- `outreach_model`：套磁文案生成使用的模型；为空时回退 `model`
- `api_key`：可直接写入密钥（不推荐）
- `api_key_env`：环境变量名；兼容直接写入密钥字符串
- `base_url`：兼容接口地址
- `timeout_seconds` `request_timeout_seconds` `connect_timeout_seconds` `max_tokens` `temperature`：请求参数
- `enabled_for_filter`：是否用于帖子过滤
- `enabled_for_jobs`：是否用于岗位抽取
- `enabled_for_summary`：是否用于摘要增强
- `enabled_for_outreach`：是否生成套磁文案（关闭后机会点岗位不再生成文案）
- `max_filter_items` `max_job_items` `max_summary_items`：每轮 LLM 处理上限
- `single_pass_extract`：是否启用“单次直提”（每条帖子一次 LLM 完成目标判断+岗位提取，默认 `true`）
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
2. 所有抓取到的帖子都会按 `note_id` 增量写入 `raw_notes`（用于更新互动数、正文补全等字段）。
3. 仅对“状态文件中不存在”的帖子执行智能处理（过滤、岗位提取、摘要、通知）。
4. 对每条新增帖子（已补正文）执行“单次直提”：一次 LLM 同时完成目标判断 + 岗位结构化提取。
5. LLM 超时或不可用时回退规则提取，并继续主流程。
6. 生成摘要并写入存储。
7. 按通知策略发送。

`auto` 与 `agent` 区别。
- `auto`：按 `llm.max_*` 限额执行，适合稳定低成本运行。
- `agent`：对更多样本做过滤/抽取/摘要，并按 `agent_send_top_n` 发送重点结果。

过滤质量控制。
- 默认走“单次直提”（LLM 一次返回 `is_target + 结构化字段`）；失败时回退规则。
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

`raw_notes` 关键字段说明。
- `publish_time_quality`：发布时间解析质量（`parsed` / `fallback`）。
- `first_seen_at`：该 `note_id` 首次入库时间。
- `updated_at`：该 `note_id` 最近一次刷新时间。

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
- 可观测性统计（阶段耗时、慢阶段、错误码）
- 配置向导（推荐配置 + 一键自检 + 修复建议）
- 30 秒自动刷新汇总

配置向导使用流程（控制中心）。
1. 点击“应用推荐配置”，自动写入关键词/排序/周期等建议值。
2. 点击“一键自检”，系统会按项检查并给出问题与修复建议。
3. 按建议修复后再次自检，全部通过后可点击“标记向导完成”。

自检状态说明。
- `pass`：当前项检查通过。
- `warn`：可运行但建议调整（如功能开关关闭、跳过网络检查）。
- `fail`：会影响功能，建议按修复建议处理后重试。

后端 API。
- `GET /api/health`
- `GET /api/summary`
- `GET /api/leads?limit=200&q=关键词`
- `GET /api/leads` 返回 `publish_time_display`（绝对时间显示字段）。
- `GET /api/runs?limit=20`
- `GET /api/setup/check`
- `POST /api/setup/check`
- `GET /api/runs` 关键字段：`stage_total_ms`、`stage_avg_ms`、`stage_failed_count`、`slow_stages`、`error_codes`

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

### 6. 为什么“岗位要求”和“原文摘要”看起来重复
- 新版本已做去重：默认不再把原文摘要回退成岗位要求。
- 若两者内容高度重合，会展示“原文与岗位要求高度重合”的提示，并建议查看原帖链接。
- 如果原帖正文本身信息很短，仍可能出现语义接近，这是源数据本身导致，不是模板重复拼接。

### 7. 终端仍出现乱码怎么办
- 优先使用项目脚本启动（`scripts/start_auto.ps1`、`scripts/start_dashboard.ps1`、`scripts/xhs_login.ps1`、`scripts/xhs_status.ps1`），脚本已内置 UTF-8 设置。
- 直接运行 Python 时优先设置：`PYTHONIOENCODING=utf-8`；不建议在 Conda 环境全局强制 `PYTHONUTF8=1`。
- 若出现 `init_import_site` 或 `UnicodeDecodeError`，先清理当前终端中的 `PYTHONUTF8` 环境变量再重试。
- 如果是历史日志文件中的旧乱码，可忽略；新运行日志会按新策略输出。

### 8. 一键自检里有失败项怎么办
- 先看失败项下方“建议”字段，按提示修复。
- 常见顺序：先修复配置文件和环境变量，再处理 XHS 登录，最后检查邮件/LLM 连通性。
- 如果只想先验证本地配置，可在 API 调用中禁用网络检查：`POST /api/setup/check` with `include_network=false`。

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
- 页面定位：
  - 线索中心：全量运营视图，适合观察抓取质量与互动变化。
  - 摘要中心：摘要成品视图，默认仅展示岗位/公司/要求/摘要，适合快速复核与发送。
- 线索列表默认分页加载，不再一次性展示全部数据。
- 分页 API：`GET /api/leads?limit=30&page=1&view=all&q=关键词`
  - `view=summary` 表示只返回有摘要的线索。
  - 响应字段包含：`items`、`total`、`page`、`page_size`、`total_pages`。
## 版本更新记录

| 版本 | 日期 | 更新内容 |
|---|---|---|
| v0.3.9 | 2026-02-26 | LLM 超时参数默认调整为 `connect=8s/read=20s`；新增 `llm.enabled_for_outreach` 开关并默认开启（`true`）；README 与示例配置同步更新。 |
| v0.3.8 | 2026-02-26 | 提取链路升级为“单次直提”：每条帖子一次 LLM 同时完成目标判断+岗位结构化提取；减少重复 LLM 调用提升速度；新增 `llm.single_pass_extract` 开关（默认开启）并保留规则回退。 |
| v0.3.7 | 2026-02-26 | 摘要中心默认改为“岗位/公司/要求/摘要”成品视图，详情面板隐藏原帖噪声字段并聚焦结构化摘要；前端脚本版本号更新以规避缓存旧布局。 |
| v0.3.6 | 2026-02-26 | `raw_notes` 升级为“每轮全量抓取结果按 `note_id` upsert”并新增 `first_seen_at/updated_at/publish_time_quality`；发布时间解析失败时保留历史时间，排序更稳定；Dashboard 线索发布时间统一为绝对时间显示。 |
| v0.3.5 | 2026-02-26 | 新增控制中心“配置向导”（应用推荐配置/标记完成）；新增“一键自检”并覆盖配置、写入权限、XHS、邮件、LLM 检查；新增 `GET/POST /api/setup/check`。 |
| v0.3.4 | 2026-02-26 | Dashboard 皮肤升级：`graphite-office` 改为深色办公主题；前端改为适度圆角；移除 `PYTHONUTF8=1` 强制设置，修复部分 Conda 环境启动报错。 |
| v0.3.3 | 2026-02-26 | 中文乱码修复增强（脚本/日志/子进程/解码链路统一 UTF-8）；LLM 文本回退策略增强；岗位通知中“岗位要求/原文摘要”去重，避免重复展示。 |
| v0.3.2 | 2026-02-25 | 新增可观测性面板：最近运行展示阶段总耗时/平均耗时/失败阶段数/慢阶段 Top/错误码分布；`/api/runs` 与 run stats 增加阶段观测字段并兼容历史快照解析。 |
| v0.3.1 | 2026-02-25 | 版本升级；LLM 过滤/结构化提取改为全量调用；终端新增降级/恢复与回退日志（full_llm/fallback）；Windows 终端中文显示优化；filter 提示词与输入字段精简提速；邮件升级为 HTML 办公风模板（无圆角、表格化）并微调字号。 |
| v0.3.0 | 2026-02-25 | 批次摘要链路改造；新增简历解析（前端上传）、双模型配置（解析/套磁）；通知新增机会点与个性化快速套磁 |
| v0.2.0 | 2026-02-25 | Dashboard 框架化（auto/fastapi/legacy 引擎切换）；前端拆分多页面（总览/控制中心/线索中心/摘要中心）；线索接口与页面支持分页；控制台功能接入页面。 |
| v0.1.0 | 2026-02-24 | 项目首版：小红书采集、LLM 过滤与摘要、结构化岗位提取、本地 Excel/CSV 落盘、邮件/微信通知、基础 Dashboard。 |

