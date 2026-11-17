# 采集工坊 · 爬虫与RPA开发平台

面向网页爬虫规则编排、自动化采集流程、代理调度、反爬对抗、结果校验与持久化发布的爬虫与RPA数据采集开发平台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 站点画像 | `site_profile` | 目标站点 | 站点编号、域名、编码格式 |
| 代理调度 | `proxy_pool` | 代理节点 | 节点编号、代理类型、IP地址 |
| 凭证管理 | `cookie_vault` | 会话凭证 | 凭证编号、关联站点、Cookie文本 |
| 频控策略 | `rate_limiter` | 请求策略 | 策略编号、目标站点、每秒上限 |
| 抽取模板 | `extract_rule` | 抽取规则 | 规则编号、目标站点、页面类型 |
| 采集任务 | `crawl_task` | 任务批次 | 任务编号、目标站点、入口URL |
| RPA脚本库 | `rpa_script` | 自动化脚本 | 脚本编号、目标应用、触发事件 |
| 采集流水线 | `data_pipeline` | 流水线段 | 段编号、输入来源、转换算子 |
| 采集仓储 | `result_store` | 结果批次 | 批次编号、关联任务、原始行数 |
| 反爬对抗 | `anti_block` | 对抗策略 | 策略编号、目标站点、触发特征 |
| 质量审计 | `quality_check` | 审计记录 | 记录编号、关联批次、检查项 |
| 增量同步 | `delta_sync` | 同步水位 | 水位编号、源数据集、增量字段 |
| 采集监控 | `log_monitor` | 监控事件 | 事件编号、事件类型、严重级别 |
| 模板市场 | `template_mgr` | 采集模板 | 模板编号、适用站点、模板类型 |
| 数据分发 | `export_hub` | 分发通道 | 通道编号、输出格式、目标地址 |
| 定时调度 | `scheduler` | 调度计划 | 计划编号、关联任务、Cron表达式 |
| 解析引擎 | `parse_engine` | 解析配置 | 配置编号、页面类型、引擎类型 |
| 重试队列 | `retry_queue` | 重试条目 | 条目编号、失败页面、失败原因 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

## 调度窗口扫描与续做

`backend/app/services/scheduler_engine.py` 把「一次调度计划到期」抽象成调度窗口，
窗口唯一键为 `(计划 id, 窗口起始分钟)`：

- 批量扫描（`POST /api/scheduler/scan`、`POST /api/scheduler/tick-all`）读取待激活/运行中的计划、
  已有 `scheduler_triggers` 触发记录与 `retry_queue` 重试条目，逐窗口判定：
  成功窗口标记「已跳过」且绝不再建采集任务；失败窗口只补建一次重试条目与
  `scheduler_resume_batches` 续做批次；到期的未记录窗口按扫描范围决定本轮或下一轮进入采集。
- 扫描范围两种取值：`include_due`（本轮纳入刚到期窗口）、`defer_due`（下一轮再纳入）。
  被推迟的窗口会先落一条 `待触发` 触发记录，下一轮复用同一条记录，不会生成重复窗口。
- 续做只有一个入口 `resume_window`（`POST /api/scheduler/resume`，重试队列页
  `POST /api/retry_queue/{id}/resume` 只是转发），续做任务批次带 `前序任务` 字段，
  原失败任务与上一轮已完成任务都不覆盖；重复调用直接跳过。
- 页面同步：定时调度页展示扫描范围、窗口分类与续做按钮；重试队列页展示待续做条目；
  采集任务页展示续做任务批次。窗口合并口径由 `GET /api/scheduler/windows` 提供。

领域：数据工程
子方向：数据采集、爬虫与RPA
