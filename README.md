# SuccessionPilot 自动找继任系统

## 版本信息
- 项目版本：`0.5.2`
- Python：`>=3.9`
- Node.js：`>=18`
- XHS MCP（vendor）：`0.8.8-local`

### v0.5.2 更新要点
- README 对齐实际代码：补充 v0.5.1 后端分层文件定位（dashboard/pipeline/agents 门面与子模块）。
- 文档结构优化：配置章节新增“覆盖优先级 / 最小可用配置 / 高频字段优先调 / 进阶参数”分层阅读路径。
- 测试说明优化：建议先跑拆分兼容性与关键回归，再按需执行全量测试。
- 解耦修复：`pipeline_service` 回退通知不再调用 `CommunicationAgent` 私有方法，改为公开接口 `build_retry_fallback_message` + 内置兜底文案，降低模块间隐式耦合。
- 真实链路验收：完成一轮 `--run-once` 实跑（抓取→详情→提取→摘要→发送全链路成功），并验证在 LLM 超时重试场景下主流程可稳定完成。

### v0.5.1 更新要点
- 后端核心分层拆分（第一阶段）：将 `dashboard_backend.py` 拆分为 API 门面 + 服务层 + 仓储层 + 运行时管理，降低单文件联动风险。
- Pipeline 结构收敛：`pipeline.py` 保留核心编排入口，仓储读写与辅助服务逻辑拆分到独立模块，减少主流程复杂度。
- Agents 模块化：`agents.py` 改为兼容门面，拆分为 `types/planner/intelligence/communication` 子模块，提升可维护性与职责清晰度。
- 兼容性保持：外部调用入口保持不变（如 `from auto_successor.dashboard_backend import DataBackend`、`from auto_successor.agents import ...`）。

### v0.5.0 更新要点
- 控制中心信息密度优化：`配置面板` 与 `简历管理` 改为可折叠高级区，默认收起，优先聚焦常用操作。
- 交互反馈升级：关键按钮支持“执行中”状态（忙碌文案 + 旋转指示），降低重复点击与误触。
- 视图切换优化：控制中心下自动隐藏搜索框，减少无关控件干扰。
- 页面可读性提升：统一上调关键文案字号并优化控制区网格布局。
- 滚动体验优化：移除详情区与侧栏的多层滚动，减少“滚错区域”的使用成本。
- 控制中心排版修复：拆分 `ops-span-2`（控制卡片）与 `span-2`（表单字段）用途，修复卡片宽度错位与响应式下的布局冲突。
- 分页体验修复：分页大小按视图记忆（`overview/leads/summary`）并持久化，切换视图后不再重置用户已选每页条数。
- 编辑保护修复：检测到“快速改字段”存在未保存改动时，自动刷新会跳过线索重载，避免输入被重绘覆盖。

### v0.4.12 更新要点
- 工作台导航改为无刷新切换：侧栏点击直接在 `dashboard.html` 内切换视图，并同步 URL 查询参数 `?view=`。
- 支持浏览器前进/后退切换视图（`popstate`），与总览/控制中心/线索中心/摘要中心保持一致。
- 前端工作区渲染收敛到 Vue 主路径：移除重复的旧 DOM 渲染分支，减少双轨逻辑维护成本与状态不一致风险。

### v0.4.11 更新要点
- 前端页面结构收敛为单入口：新增 `web/dashboard.html` 作为唯一完整页面模板（总览/控制中心/线索中心/摘要中心通过 `?view=` 切换）。
- 兼容旧链接：`index.html`、`control.html`、`leads.html`、`summary.html` 变为轻量跳转页，历史书签仍可用。
- 控制面板数据继续按需加载（仅在控制中心视图触发），减少无效请求并降低维护成本。

### v0.4.10 更新要点
- 前端容错升级：`/api/retry-queue` 异常或未提供时自动降级，不再导致整页出现 `API unavailable`。
- 刷新策略优化：控制中心数据按页面按需加载，页面不可见时暂停轮询，回到前台自动补拉。
- 交互与文案优化：运行详情/线索详情核心文案统一中文；线索行与运行记录支持键盘选择（Enter/空格）并增加焦点高亮。
- 页面冗余收敛：`index/leads/summary` 页面移除控制中心静态块，控制区统一由单页模板承载。

### v0.4.9 更新要点
- 控制中心告警配置升级为“双窗口可视化配置”：可直接配置短窗/长窗的窗口轮数、阈值、最小样本（或最小轮数）。
- 前端保存配置时同时写入双窗口字段与兼容旧字段，避免覆盖已有告警策略。

### v0.4.8 更新要点
- 告警从单阈值升级为双窗口：短窗口用于识别突发，长窗口用于识别趋势，减少误报与告警疲劳。
- 三类指标全部支持双窗口判定：`fetch_fail_streak`、`llm_timeout_rate`、`detail_missing_rate`。
- 保留旧配置兼容：`fetch_fail_streak_threshold` / `llm_timeout_rate_threshold` / `detail_missing_rate_threshold` 仍可使用，并自动映射到短窗口配置。

### v0.4.7 更新要点
- 新增前端“质量面板”：展示字段完整率（公司/岗位/地点/要求）、结构化完整率、正文覆盖率。
- 新增质量趋势：最近运行的提取命中率、详情覆盖率、LLM 成功率趋势（按 run 展示）。
- `/api/performance` 增加 `quality` 聚合字段，便于页面和外部监控统一读取质量指标。

### v0.4.6 更新要点
- 新增阈值告警能力：支持连续抓取失败、LLM 超时率、详情缺失率三类告警自动评估与自动提醒。
- 新增告警冷却：同类告警按 `cooldown_minutes` 限流，避免每轮重复刷屏。
- 运行快照增强：`stats` 新增 `llm_timeout_rate/detail_missing_rate/alerts_*` 字段。
- 性能看板增强：新增告警触发总数、已通知总数、触发轮次占比与告警码分布。
- 控制中心配置面板新增告警参数可视化配置（阈值、样本、冷却、通道）。

### v0.4.5 更新要点
- 控制中心“配置向导”整块支持折叠/展开（默认展开），减少页面占用并便于聚焦其他操作区。
- 配置向导的“一键自检结果”升级为可折叠视图：每项可展开/收起，默认展开失败和警告项，通过项默认折叠。
- 新增自检结果快捷操作：`展开全部`、`收起通过项`，便于集中处理异常项。
- 自检结果按状态优先级排序（失败 > 警告 > 通过），问题项自动前置。
- 前端静态资源版本更新为 `web/app.js?v=20260227-8`（仅缓存版本升级，无新增配置字段）。

### v0.4.4 更新要点
- 前端工作区（线索列表/摘要列表/详情面板/运行记录）改为 Vue 响应式渲染，保留现有办公风样式与交互结构。
- 运行记录详情加载链路统一：页面点击 run 记录通过 `__spLoadRunDetail` 桥接，避免旧 DOM 与新状态不同步。
- 四个页面统一加载 `Vue 3`（CDN），并将前端脚本缓存版本更新为 `web/app.js?v=20260227-7`。
- 配置项无新增字段：`config/config.yaml`、`.env` 继续沿用现有配置即可。

### v0.4.3 更新要点
- 提取链路升级为每条 note 一个显式 NoteAgent 任务，按 `pipeline.process_workers` 并行处理，单条失败回退不阻塞其他条。
- 岗位提取取消 LLM 配额截断：进入处理链路的帖子改为全量尝试 LLM（不可用时自动回退规则）。
- 配置与文档同步：`llm.max_job_items` 标记为弃用，`config.example.yaml` 移除该字段示例。

### v0.4.2 更新要点
- 线索快速编辑：详情面板新增“快速改字段”，可直接修改 `title/company/position/location/requirements/summary/detail_text`，并通过 `POST /api/leads/update` 回写 `output.xlsx`。
- 前端交互修复：左侧栏与右侧详情面板在桌面端固定显示；点击线索行改为“只更新选中态+详情”，不再整表重绘，减少跳动与滚动位置丢失。
- 发布时间一致性修复：统一将“无时区 ISO 时间”按 UTC 解释；`first_seen_at/updated_at/sent_at/created_at` 改为带时区写入；相对时间（如“xx分钟前”）不再将已存发布时间向更晚方向漂移。

### v0.4.1 更新要点
- 详情抓取并行化：新增 `xhs.detail_workers`（默认 `3`），`collector.enrich_note_details` 支持并发抓取 detail，减少正文补全阶段耗时。
- 前端性能看板升级：新增“性能看板”区域，展示最近运行的耗时分位（均值/P50/P95）、阶段失败率、详情成功率、慢阶段热点和错误码分布。
- Dashboard API 新增：`GET /api/performance`，可用于页面与外部监控读取聚合性能指标。

### v0.4.0 更新要点
- 提取并行能力：新增 `pipeline.process_workers`（默认 `4`），支持“先抓取、后并行提取”。
- 并行覆盖阶段：`单次直提` 与 `筛选+岗位结构化` 两条链路都支持线程池并行处理。
- 顺序稳定：并行处理后仍按发布时间排序输出，不影响前端展示与发送顺序。

### v0.3.16 更新要点
- 详情抓取策略调整：`xhs.max_detail_fetch` 调整为 `18`，每轮优先做近全量 detail 抓取，提高岗位字段完整度。
- 提取流程简化：移除“目标岗位二次补全”阶段，回归单阶段提取链路，降低流程复杂度。
- 行为说明：单轮总耗时会增加，主要体现在详情抓取与后续结构化提取阶段。

### v0.3.15 更新要点
- 失败重试队列升级为任务化执行：新增 `lease_until`、`last_error_code`、`last_duration_ms`、`last_trace_id`，并支持运行中超时任务自动回收。
- 新增死信队列与幂等保障：达到最大重试自动进入 dead-letter；邮件/超时重试支持 `idempotency_key`，避免 at-least-once 下重复发送。
- 可观测性增强：控制中心重试面板可直接查看错误码、耗时、Trace、死信记录与处理成功/失败统计。
- API 统一错误模型：接口错误统一输出 `code/reason/fix_command/trace_id`，前端可直接展示可执行修复建议。

### v0.3.14 更新要点
- Dashboard API 扩展：新增运行详情与重试队列接口（`GET /api/runs/{run_id}`、`GET/POST /api/retry-queue*`），支持页面查看失败原因并执行重试/丢弃/批量唤醒。
- 控制台联动增强：线索筛选新增状态与去重维度，运行进度可实时显示阶段进展，运行记录支持下钻查看阶段耗时与错误码。
- 稳定性修复：`scripts/start_dashboard.ps1` 启动时注入项目 `src` 到 `PYTHONPATH`，避免命中旧安装包导致接口 404。

### v0.3.13 更新要点
- 新增失败重试队列：抓取失败、LLM 超时、邮件失败分队列持久化（`data/retry_queue.json`）。
- 新增后台重放线程：按批次自动重放重试任务，不阻塞主流程抓取与入库。
- 新增多账号切换：`xhs.account` + `xhs.account_cookies_dir`，控制中心可选账号并用于登录/状态检查/抓取详情。
- 运行观测增强：run stats 增加重试队列指标（pending/running/enqueued/retried/succeeded/dropped）。

### v0.3.12 更新要点
- 原文摘要质量修复：新增链接噪声拦截，纯 URL/图片 CDN 链接不再作为正文进入 `detail_text` 与摘要。
- 行内链接清洗：正文中“文字 + 链接”场景会保留文字、移除链接，避免摘要出现图片地址。
- 评论预览清洗增强：评论中的纯链接片段会被过滤，不再污染后续 LLM 摘要输入。
- 回归测试补充：新增 `xhs_collector` 文本清洗用例，覆盖“图片链接丢弃/行内链接移除/评论链接过滤”。

### v0.3.11 更新要点
- 提取链路修复：XHS 子进程输出改为字节级解码并按 `utf-8/utf-8-sig/gb18030` 自动判定，优先保证 JSON 与中文正文在入口侧解码正确。
- 文本处理收敛：`clean_line` 不再做自动转码修复，避免把正常中文误转为乱码，减少“提取前即污染”。
- 提取约束增强：岗位结构化提示词补充 `company/location` 输出约束，降低“急招/找继任”等词混入公司字段。
- 验证通过：单次全流程运行成功（抓取、结构化、摘要通知），并新增编码相关单测。

### v0.3.10 更新要点
- LLM 稳定性优化：熔断/冷却从全局改为按阶段隔离（`filter/job/summary/batch_summary/outreach`），`outreach` 失败不再拖累 `job` 提取。
- 字段质量优化：岗位公司字段新增“招/急招/找继任”等噪声前后缀清洗，减少公司名被污染。
- 地点修复：增加常见乱码地点修复（如 `鍖椾含`、`骞垮窞`），并统一归一到标准城市名用于展示与排序。

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
  max_detail_fetch: 18
  detail_workers: 3
  account: "default"
  account_cookies_dir: "~/.xhs-mcp/accounts"

pipeline:
  process_workers: 4

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

retry:
  enabled: true
  worker_interval_seconds: 12
  replay_batch_size: 3

observability:
  alerts:
    enabled: true
    cooldown_minutes: 60
    channels: [] # 留空则复用 digest_channels
    # 兼容旧字段（短窗口别名）
    fetch_fail_streak_threshold: 2
    llm_timeout_rate_threshold: 0.35
    llm_timeout_min_calls: 6
    detail_missing_rate_threshold: 0.45
    detail_missing_min_samples: 6
    # 双窗口（运行时以这里为准）
    fetch_fail_streak:
      short_window_runs: 1
      short_threshold: 2
      short_min_runs: 1
      long_window_runs: 6
      long_threshold: 1.2
      long_min_runs: 3
    llm_timeout_rate:
      short_window_runs: 1
      short_threshold: 0.35
      short_min_samples: 6
      long_window_runs: 8
      long_threshold: 0.25
      long_min_samples: 18
    detail_missing_rate:
      short_window_runs: 1
      short_threshold: 0.45
      short_min_samples: 6
      long_window_runs: 8
      long_threshold: 0.32
      long_min_samples: 18

resume:
  source_txt_path: "config/resume.txt"
  resume_text_path: "data/resume_text.txt"
  max_chars: 6000
```

简历上下文说明。
- `config/resume.example.txt` 只是模板文件，不会被程序直接读取。
- 程序实际读取的是 `resume.source_txt_path`（默认 `config/resume.txt`），并同步写入 `resume_text_path`（默认 `data/resume_text.txt`）。
- 复制 `config/resume.example.txt` 到 `config/resume.txt` 后再填入真实简历内容（TXT）。
- 运行时由 `resume_loader` 读取并裁剪，供 LLM 在岗位结构化提取、匹配度估计、批次摘要与机会点套磁文案复用。
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
打开 `http://127.0.0.1:8787/dashboard.html?view=control`，按顺序操作。
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
- `src/auto_successor/`：主业务代码（采集、智能处理、通知、Dashboard API）
- `config/`：配置模板与主配置
- `.env`：密钥与账号环境变量
- `scripts/`：启动、登录、自检相关脚本
- `web/`：Dashboard 前端页面
- `data/`：本地数据、状态、运行快照（运行后生成）
- `tests/`：回归与兼容性测试
- `docs/`：设计说明、实施报告等项目文档

## 快速定位（文件在哪）
- 主配置文件：`config/config.yaml`
- 配置模板：`config/config.example.yaml`
- 你的简历：`config/resume.txt`
- 简历模板：`config/resume.example.txt`
- 环境变量模板：`.env.example`
- 本地环境变量：`.env`
- 前端主页：`web/dashboard.html`
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

后端核心（v0.5.1 分层后）：
- Dashboard API 门面：`src/auto_successor/dashboard_backend.py`
- Dashboard 服务层：`src/auto_successor/dashboard_service.py`
- Dashboard 仓储层：`src/auto_successor/dashboard_repository.py`
- Dashboard 运行时：`src/auto_successor/dashboard_runtime_manager.py`
- Pipeline 主编排：`src/auto_successor/pipeline.py`
- Pipeline 服务层：`src/auto_successor/pipeline_service.py`
- Pipeline 仓储层：`src/auto_successor/pipeline_repository.py`
- Agents 门面：`src/auto_successor/agents.py`
- Agents 子模块：`src/auto_successor/agents_{types,planner,intelligence,communication}.py`

## 后端分层说明（v0.5.1）
- **API 层**：对外暴露稳定入口（例如 `DataBackend` / `AutoSuccessorPipeline` / `agents` 门面）。
- **服务层（Service）**：业务编排与规则判断，不直接耦合具体存储格式。
- **仓储层（Repository）**：文件/表格/快照等读写细节，尽量保持低耦合、可替换。
- 维护建议：新增功能优先放在 Service/Repository，不要把 API 门面重新做大。

## 环境要求
- Python 3.9 及以上
- Node.js 18 及以上
- Google Chrome（用于 XHS MCP 登录与抓取）
- Windows PowerShell（示例命令按 Windows 编写）
- Dashboard 前端默认从 CDN 加载 Vue 3（`https://unpkg.com/vue@3/dist/vue.global.prod.js`）；若网络不可达会自动回退到 legacy 渲染。

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

配置覆盖优先级（高 → 低）：
1. 命令行参数（如 `--mode`、`--interval-minutes`）
2. `config/config.yaml`
3. `.env`（用于密钥与账号类变量）
4. `config.py` 中的默认值

### 最小可用配置（先跑起来）
如果你想先稳定跑通，再做精细调参，可先保证下列核心字段：

```yaml
app:
  interval_minutes: 15

xhs:
  keyword: "继任"
  max_results: 20
  max_detail_fetch: 18
  detail_workers: 3

notification:
  mode: "digest"
  digest_interval_minutes: 30
  digest_channels: ["email"]
```

同时在 `.env` 配置最小邮件参数（若使用邮件）：
- `EMAIL_SMTP_USERNAME`
- `EMAIL_SMTP_PASSWORD`
- `EMAIL_FROM`
- `EMAIL_TO`

### 高频字段（建议优先调）
- 抓取量：`xhs.max_results`
- 详情补全：`xhs.max_detail_fetch`、`xhs.detail_workers`
- 运行频率：`app.interval_minutes`
- 运行模式：`agent.mode`（`auto` / `agent`）
- 提取并发：`pipeline.process_workers`
- 通知策略：`notification.mode`、`notification.digest_interval_minutes`
- 摘要通道：`notification.digest_channels`
- LLM 总开关：`llm.enabled`
- LLM 直提模式：`llm.single_pass_extract`
- 重试开关：`retry.enabled`

### 模块详细参数（进阶）

### app
- `timezone`：时区，例如 `Asia/Shanghai`
- `log_level`：日志级别
- `interval_minutes`：循环模式间隔分钟数

### pipeline
- `min_confidence`：规则链路基础阈值
- `process_workers`：提取阶段并行线程数（默认 `4`，建议 `2-6`）

### xhs
- `command`：执行命令，通常为 `node`
- `args`：XHS MCP 主脚本路径
- `browser_path`：Chrome 可执行文件路径
- `account`：抓取与登录使用的账号标识（`default` 表示 `~/.xhs-mcp/cookies.json`）
- `account_cookies_dir`：多账号 Cookies 目录（支持 `<dir>/<account>.json` 或 `<dir>/<account>/cookies.json`）
- `search_sort`：搜索排序策略
- `keyword`：搜索关键词，建议固定为 `继任`
- `max_results`：每轮最大抓取数量
- `max_detail_fetch`：每轮详情抓取上限（当前建议 `18`）
- `detail_workers`：详情抓取并行线程数（默认 `3`，建议 `2-5`）
- 建议将 `max_detail_fetch` 调整到 `18`（或接近 `max_results`）；若该值过低，容易出现“帖子有正文但岗位要求/公司/岗位字段不完整”。
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
- `max_job_items`：兼容字段（默认不建议依赖；开启 `single_pass_extract` 时通常不作为主控阈值）
- `max_filter_items` `max_summary_items`：兼容字段
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

### retry
- `enabled`：是否启用失败重试队列
- `worker_interval_seconds`：后台重放轮询间隔（秒）
- `replay_batch_size`：每轮重放任务数
- `fetch_max_attempts`：抓取失败最大重试次数
- `llm_timeout_max_attempts`：LLM 超时最大重试次数
- `email_max_attempts`：邮件失败最大重试次数
- `base_backoff_seconds`：指数退避起始秒数
- `max_backoff_seconds`：指数退避上限秒数

### observability.alerts
- `enabled`：是否启用阈值告警
- `cooldown_minutes`：同类告警冷却时间（分钟）
- `fetch_fail_streak_threshold`：兼容旧字段，映射到 `fetch_fail_streak.short_threshold`
- `llm_timeout_rate_threshold`：兼容旧字段，映射到 `llm_timeout_rate.short_threshold`
- `llm_timeout_min_calls`：兼容旧字段，映射到 `llm_timeout_rate.short_min_samples`
- `detail_missing_rate_threshold`：兼容旧字段，映射到 `detail_missing_rate.short_threshold`
- `detail_missing_min_samples`：兼容旧字段，映射到 `detail_missing_rate.short_min_samples`
- `fetch_fail_streak.*`：双窗口配置（短窗 `max(fetch_fail_streak)` + 长窗 `avg(fetch_fail_streak)`）
- `llm_timeout_rate.*`：双窗口配置（短窗/长窗按样本加权超时率）
- `detail_missing_rate.*`：双窗口配置（短窗/长窗按样本加权缺失率）
- `channels`：告警通道，留空则复用 `notification.digest_channels`

行为说明。
- 告警按“双窗口”评估：短窗口识别突发、长窗口识别趋势，必须同时满足才触发通知。
- 抓取失败（登录/搜索/详情）、LLM 超时、邮件失败会分别入队。
- 队列持久化文件默认：`data/retry_queue.json`。
- 重放在后台线程执行，不阻塞主流程抓取、入库和当前轮通知。
- 重试超过最大次数会进入死信（dead-letter），可在控制中心查看并手动重试/丢弃。
- 邮件与超时重试支持幂等键（`idempotency_key`），完成过的任务不会重复执行。

`config/config.example.yaml` 默认值速览（节选）：

| 分类 | 默认值 |
|---|---|
| `xhs.search_sort` | `time_descending` |
| `xhs.detail_workers` | `3` |
| `pipeline.process_workers` | `4` |
| `notification.mode` | `digest` |
| `notification.digest_interval_minutes` | `30` |
| `notification.digest_send_when_no_new` | `false` |
| `notification.attach_excel` | `false` |
| `notification.attach_jobs_csv` | `false` |
| `observability.alerts.enabled` | `true` |
| `observability.alerts.cooldown_minutes` | `60` |

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
- `retry_queue_path`：失败重试队列持久化文件路径（默认 `data/retry_queue.json`）

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
  account: "default"
  account_cookies_dir: "~/.xhs-mcp/accounts"
  search_sort: "time_descending"
  keyword: "继任"
```

多账号切换（控制中心）。
- 打开 `http://127.0.0.1:8787/dashboard.html?view=control`。
- 在“XHS 账号”下拉框选择账号；在“账号 Cookies 目录”填写账号文件目录。
- 点击“保存配置”后生效，后续登录检查、扫码登录、抓取都会使用所选账号。
- 若账号文件不存在，可先选中该账号执行一次扫码登录，系统会自动写回对应账号 Cookies 文件。

### 2. 登录状态检查
推荐使用脚本。
```powershell
powershell -ExecutionPolicy Bypass -File scripts/xhs_status.ps1
# 指定账号（可选）
powershell -ExecutionPolicy Bypass -File scripts/xhs_status.ps1 -Account acc-a -AccountCookiesDir "~/.xhs-mcp/accounts"
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
# 指定账号（可选）
powershell -ExecutionPolicy Bypass -File scripts/xhs_login.ps1 -Timeout 180 -Account acc-a -AccountCookiesDir "~/.xhs-mcp/accounts"
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
- 详情区快速改字段并回写本地数据表（`output.xlsx`）
- 桌面端双栏固定（左侧导航 + 右侧详情），减少滚动跳转
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
- `POST /api/leads/update`：前端快速改字段（`title/company/position/location/requirements/summary/detail_text`）并回写 `output.xlsx`
- `GET /api/runs?limit=20`
- `GET /api/performance?limit=50`
- `GET /api/xhs/accounts`
- `GET /api/setup/check`
- `POST /api/setup/check`
- `GET /api/runs` 关键字段：`stage_total_ms`、`stage_avg_ms`、`stage_failed_count`、`slow_stages`、`error_codes`
- `GET /api/performance` 聚合字段：`stage_total_ms(avg/p50/p95)`、`stage_failed_rate`、`detail_success_rate`、`slow_stages`、`error_codes`
- `GET /api/runs` 重试字段：`retry_pending`、`retry_running`、`retry_enqueued`、`retry_retried`、`retry_succeeded`、`retry_dropped`
- `GET /api/retry-queue`：返回 `items`、`dead_letters` 与 `summary`（含 dead-letter 与处理耗时统计）
- 错误响应统一格式：`{ ok: false, error: { code, message, reason, fix_command, trace_id } }`

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

### 9. 程序是不是在用 `resume.example`？
- 不会。`config/resume.example.txt` 仅用于示例。
- 实际使用 `config/resume.txt`（或 `resume.source_txt_path` 指定的路径）。
- 如果运行日志里出现 `resume_chars: 0`，说明当前未读取到有效简历文本；此时匹配度和套磁会走无简历上下文的兜底策略。

## 测试
```powershell
# 推荐：先跑拆分兼容性与关键回归（更快）
python -m unittest tests.test_split_compatibility
python -m unittest tests.test_dashboard_backend_core

# 需要更完整验证时再跑全量
python -m unittest discover -s tests
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

- 主入口（推荐）：
  - `http://127.0.0.1:8787/dashboard.html?view=overview`（总览）
  - `http://127.0.0.1:8787/dashboard.html?view=control`（控制中心）
  - `http://127.0.0.1:8787/dashboard.html?view=leads`（线索中心）
  - `http://127.0.0.1:8787/dashboard.html?view=summary`（摘要中心）
- 同页导航：侧栏切换视图为无刷新模式，URL 中 `?view=` 会同步更新，可直接复制分享当前视图地址。
- 兼容入口（自动跳转到主入口）：
  - `http://127.0.0.1:8787/index.html`
  - `http://127.0.0.1:8787/control.html`
  - `http://127.0.0.1:8787/leads.html`
  - `http://127.0.0.1:8787/summary.html`
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
| v0.5.2 | 2026-03-04 | README 对齐与可读性优化：补充分层后后端文件定位（dashboard/pipeline/agents），重构配置章节为“覆盖优先级 + 最小可用 + 高频字段 + 进阶参数”，并将测试建议调整为先跑兼容性与关键回归；修复回退通知对 `CommunicationAgent` 私有方法的隐式耦合，并完成一轮真实 `--run-once` 链路验收。 |
| v0.5.1 | 2026-03-04 | 后端核心重构：`dashboard` 按 API/服务/仓储/运行时分层；`pipeline` 拆分为主编排 + 服务 + 仓储；`agents` 拆分为类型/规划/智能/通信模块并保留原导入兼容，降低超大文件联动风险并提升可维护性。 |
| v0.5.0 | 2026-03-03 | 前端可用性专项优化：控制中心高级配置改为可折叠（默认收起），关键按钮新增执行中状态，控制中心隐藏搜索框；上调关键字体尺寸并优化控制区栅格；减少侧栏/详情多层滚动，提升办公场景可读性与操作稳定性；修复 `ops-span-2` 与 `span-2` 栅格冲突导致的控制中心排版错位；分页大小按视图记忆并持久化；未保存“快速改字段”时自动刷新跳过线索重载，避免编辑内容被覆盖。 |
| v0.4.12 | 2026-03-03 | 工作台导航支持无刷新视图切换并同步 `?view=`；支持浏览器前进/后退视图切换；工作区渲染逻辑收敛到 Vue 主路径，移除重复 DOM 分支，降低维护复杂度。 |
| v0.4.11 | 2026-03-03 | 前端结构收敛为单入口 `dashboard.html`（通过 `?view=` 切换总览/控制/线索/摘要）；旧 `index/control/leads/summary` 保留为兼容跳转页；控制面板数据继续按视图按需加载，减少模板冗余与维护成本。 |
| v0.4.10 | 2026-03-03 | 前端容错升级：重试队列接口异常/缺失时自动降级，不再阻塞整页；控制中心改为按需加载配置/简历/重试队列并结合页面可见性降频轮询；统一关键中文文案并补齐键盘可访问性（线索行/运行记录支持 Enter/空格，增加焦点高亮）；`index/leads/summary` 移除控制中心静态块。 |
| v0.4.9 | 2026-03-01 | 控制中心告警配置支持双窗口可视化编辑（短窗/长窗窗口轮数、阈值、最小样本）；前端保存时同步写入双窗口与兼容旧字段，避免配置回退。 |
| v0.4.8 | 2026-03-01 | 告警升级为双窗口（短窗突发+长窗趋势）并覆盖 `fetch_fail_streak`、`llm_timeout_rate`、`detail_missing_rate`；保留旧阈值字段兼容并自动映射到短窗口；控制中心配置读写同步兼容双窗口字段。 |
| v0.4.7 | 2026-03-01 | 新增前端质量面板（字段完整率、结构化完整率、正文覆盖率）；`/api/performance` 新增 `quality` 聚合字段；新增最近运行质量趋势（提取命中率/详情覆盖率/LLM 成功率）与缺失字段 Top。 |
| v0.4.6 | 2026-02-28 | 新增阈值告警（连续抓取失败、LLM 超时率、详情缺失率）与冷却控制；run stats 增加 `llm_timeout_rate/detail_missing_rate/alerts_*`；性能看板新增告警聚合与告警码分布；控制中心可配置告警参数与通道。 |
| v0.4.5 | 2026-02-27 | 控制中心“配置向导”整块支持折叠/展开；自检结果支持折叠/展开与“展开全部/收起通过项”；结果按失败/警告/通过排序；前端缓存版本升级为 `app.js?v=20260227-8`。 |
| v0.4.4 | 2026-02-27 | 前端工作区改为 Vue 响应式渲染（保留原样式）；运行记录详情改为 `__spLoadRunDetail` 桥接；四个页面统一接入 Vue CDN 并更新 `app.js` 缓存版本；本次无新增配置字段。 |
| v0.4.3 | 2026-02-27 | 提取链路改为每帖 NoteAgent 并行；岗位提取改为全量 LLM 尝试（取消预算截断）；`llm.max_job_items` 标记弃用并同步配置示例。 |
| v0.4.2 | 2026-02-27 | 新增线索“快速改字段”并回写 `output.xlsx`（`POST /api/leads/update`）；前端修复双栏固定与点击不重绘；统一无时区时间按 UTC 解析并修复相对发布时间漂移。 |
| v0.4.1 | 2026-02-27 | 新增 `xhs.detail_workers` 并行 detail 抓取（默认 3）；控制中心与总览新增性能看板（耗时均值/P50/P95、失败率、慢阶段、错误码）；Dashboard 新增 `GET /api/performance`。 |
| v0.4.0 | 2026-02-27 | 新增 `pipeline.process_workers` 并发提取参数（默认 4）；实现“先抓取后并行处理”（单次直提与筛选+结构化均支持）；并行后仍保持发布时间排序稳定。 |
| v0.3.16 | 2026-02-27 | `xhs.max_detail_fetch` 调整为 18（近全量详情抓取）；移除“目标岗位二次补全”阶段，回归单阶段提取；说明单轮耗时会相应上升。 |
| v0.3.15 | 2026-02-27 | 重试队列任务化升级（lease/error_code/duration/trace）；新增 dead-letter 与幂等键防重复发送；控制中心可视化死信与重试观测；API 错误统一为 `code/reason/fix_command/trace_id`。 |
| v0.3.14 | 2026-02-27 | Dashboard 新增运行详情与重试队列 API（含重试/丢弃/批量唤醒）；控制中心联动支持状态/去重筛选与运行详情下钻；`start_dashboard.ps1` 注入项目 `src` 路径，修复旧安装包抢占导致的接口 404。 |
| v0.3.13 | 2026-02-26 | 新增失败重试队列（抓取/LLM超时/邮件分队列）与后台重放；新增 XHS 多账号配置（`xhs.account`、`xhs.account_cookies_dir`）及控制中心账号选择；运行统计新增重试指标。 |
| v0.3.12 | 2026-02-26 | 新增正文/评论链接噪声拦截：纯图片链接不再进入原文摘要；“文字+链接”保留文字并移除链接；补充对应单元测试。 |
| v0.3.11 | 2026-02-26 | 提取入口改为字节级解码（`utf-8/utf-8-sig/gb18030` 自动判定）；`clean_line` 停止自动转码避免正常中文被误改；岗位提取提示词补充 `company/location` 约束；新增编码相关单测。 |
| v0.3.10 | 2026-02-26 | LLM 熔断改为按阶段隔离（`job` 与 `outreach`互不影响）；公司字段新增招聘口号清洗；地点新增常见乱码修复并归一为标准城市名。 |
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

