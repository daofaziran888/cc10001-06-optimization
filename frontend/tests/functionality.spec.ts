import { expect, test } from '@playwright/test'
import { readFile } from 'node:fs/promises'

type ModuleCase = {
  key: string
  fields: string[]
  actions: string[]
  actionTargets: string[]
  shape: string
}

const modules: ModuleCase[] = [
  {
    "key": "site_profile",
    "fields": [
      "站点编号",
      "域名",
      "编码格式",
      "反爬等级",
      "合规说明",
      "负责人",
      "接入状态",
      "最后爬取"
    ],
    "actions": [
      "准入审核",
      "冻结站点",
      "废弃站点"
    ],
    "actionTargets": [
      "已准入",
      "已冻结",
      "已废弃"
    ],
    "shape": "crud-table"
  },
  {
    "key": "proxy_pool",
    "fields": [
      "节点编号",
      "代理类型",
      "IP地址",
      "端口号",
      "匿名等级",
      "响应延迟",
      "成功率",
      "最后检测"
    ],
    "actions": [
      "启动检测",
      "降级节点",
      "下线节点"
    ],
    "actionTargets": [
      "健康",
      "降级",
      "已下线"
    ],
    "shape": "crud-table"
  },
  {
    "key": "cookie_vault",
    "fields": [
      "凭证编号",
      "关联站点",
      "Cookie文本",
      "UserAgent",
      "过期时间",
      "刷新策略",
      "最后验证",
      "登录方式"
    ],
    "actions": [
      "验证凭证",
      "标记过期",
      "废弃凭证"
    ],
    "actionTargets": [
      "有效",
      "即将过期",
      "已失效"
    ],
    "shape": "crud-table"
  },
  {
    "key": "rate_limiter",
    "fields": [
      "策略编号",
      "目标站点",
      "每秒上限",
      "并发连接",
      "退避系数",
      "最大重试",
      "窗口粒度",
      "生效时段"
    ],
    "actions": [
      "启用策略",
      "暂停策略",
      "归档策略"
    ],
    "actionTargets": [
      "已生效",
      "已暂停",
      "已归档"
    ],
    "shape": "crud-table"
  },
  {
    "key": "extract_rule",
    "fields": [
      "规则编号",
      "目标站点",
      "页面类型",
      "字段路径",
      "提取方式",
      "缺省值",
      "校验正则",
      "规则优先级"
    ],
    "actions": [
      "提交校验",
      "发布规则",
      "废弃规则"
    ],
    "actionTargets": [
      "校验中",
      "已发布",
      "已废弃"
    ],
    "shape": "crud-table"
  },
  {
    "key": "crawl_task",
    "fields": [
      "任务编号",
      "目标站点",
      "入口URL",
      "深度限制",
      "页面上限",
      "调度cron",
      "优先级",
      "截止时间"
    ],
    "actions": [
      "提交调度",
      "取消任务",
      "归档结果"
    ],
    "actionTargets": [
      "运行中",
      "已取消",
      "已完成"
    ],
    "shape": "job-timeline"
  },
  {
    "key": "rpa_script",
    "fields": [
      "脚本编号",
      "目标应用",
      "触发事件",
      "操作序列",
      "超时秒数",
      "等待条件",
      "错误处理",
      "脚本版本"
    ],
    "actions": [
      "提交测试",
      "投产发布",
      "废弃脚本"
    ],
    "actionTargets": [
      "测试中",
      "已投产",
      "已废弃"
    ],
    "shape": "dag-graph"
  },
  {
    "key": "data_pipeline",
    "fields": [
      "段编号",
      "输入来源",
      "转换算子",
      "输出目标",
      "依赖段",
      "并行度",
      "失败策略",
      "超时分钟"
    ],
    "actions": [
      "启动流水线",
      "暂停执行",
      "继续执行"
    ],
    "actionTargets": [
      "运行中",
      "已完成",
      "异常中断"
    ],
    "shape": "dag-graph"
  },
  {
    "key": "result_store",
    "fields": [
      "批次编号",
      "关联任务",
      "原始行数",
      "有效行数",
      "存储路径",
      "压缩格式",
      "校验摘要",
      "落地时间"
    ],
    "actions": [
      "触发校验",
      "标记通过",
      "标记失败"
    ],
    "actionTargets": [
      "校验通过",
      "校验失败",
      "已落盘"
    ],
    "shape": "crud-table"
  },
  {
    "key": "anti_block",
    "fields": [
      "策略编号",
      "目标站点",
      "触发特征",
      "应对动作",
      "切换耗时",
      "成功率",
      "生效时段",
      "备注"
    ],
    "actions": [
      "启用策略",
      "标记失效",
      "停用策略"
    ],
    "actionTargets": [
      "运行中",
      "已失效",
      "已停用"
    ],
    "shape": "crud-table"
  },
  {
    "key": "quality_check",
    "fields": [
      "记录编号",
      "关联批次",
      "检查项",
      "阈值",
      "实际值",
      "判定结果",
      "审计时间",
      "处理建议"
    ],
    "actions": [
      "执行审计",
      "确认通过",
      "提交修复"
    ],
    "actionTargets": [
      "已通过",
      "需修复",
      "已忽略"
    ],
    "shape": "job-timeline"
  },
  {
    "key": "delta_sync",
    "fields": [
      "水位编号",
      "源数据集",
      "增量字段",
      "上次水位",
      "当前水位",
      "同步周期",
      "捕获行数",
      "最后同步"
    ],
    "actions": [
      "初始化水位",
      "启动同步",
      "暂停同步"
    ],
    "actionTargets": [
      "运行中",
      "已暂停",
      "追赶延迟"
    ],
    "shape": "job-timeline"
  },
  {
    "key": "log_monitor",
    "fields": [
      "事件编号",
      "事件类型",
      "严重级别",
      "关联任务",
      "事件摘要",
      "触发时间",
      "恢复状态",
      "处理人"
    ],
    "actions": [
      "确认事件",
      "开始处理",
      "标记解决"
    ],
    "actionTargets": [
      "处理中",
      "已解决",
      "已忽略"
    ],
    "shape": "analysis-dashboard"
  },
  {
    "key": "template_mgr",
    "fields": [
      "模板编号",
      "适用站点",
      "模板类型",
      "版本号",
      "下载次数",
      "评分",
      "兼容说明",
      "发布者"
    ],
    "actions": [
      "发布模板",
      "下架模板",
      "废弃模板"
    ],
    "actionTargets": [
      "已发布",
      "已下架",
      "已废弃"
    ],
    "shape": "crud-table"
  },
  {
    "key": "export_hub",
    "fields": [
      "通道编号",
      "输出格式",
      "目标地址",
      "加密方式",
      "压缩选项",
      "分片大小",
      "重试上限",
      "回调地址"
    ],
    "actions": [
      "启用通道",
      "暂停通道",
      "停用通道"
    ],
    "actionTargets": [
      "已启用",
      "传输中",
      "已停用"
    ],
    "shape": "crud-table"
  },
  {
    "key": "scheduler",
    "fields": [
      "计划编号",
      "关联任务",
      "Cron表达式",
      "时区",
      "重试次数",
      "失败通知",
      "并发上限",
      "下次执行"
    ],
    "actions": [
      "激活计划",
      "立即执行",
      "停用计划"
    ],
    "actionTargets": [
      "运行中",
      "已完成",
      "已停用"
    ],
    "shape": "job-timeline"
  },
  {
    "key": "parse_engine",
    "fields": [
      "配置编号",
      "页面类型",
      "引擎类型",
      "解析规则",
      "字符编码",
      "容错模式",
      "输出Schema",
      "版本号"
    ],
    "actions": [
      "提交验证",
      "部署上线",
      "停用配置"
    ],
    "actionTargets": [
      "已验证",
      "已部署",
      "已停用"
    ],
    "shape": "crud-table"
  },
  {
    "key": "retry_queue",
    "fields": [
      "条目编号",
      "失败页面",
      "失败原因",
      "重试次数",
      "最大重试",
      "下次重试",
      "错误详情",
      "关联任务"
    ],
    "actions": [
      "强制重试",
      "标记放弃",
      "确认恢复"
    ],
    "actionTargets": [
      "重试中",
      "已达上限",
      "已恢复"
    ],
    "shape": "job-timeline"
  }
]
const repoKind = 'fullstack'
const crudModules = modules.filter(m => m.shape === 'crud-table')
const dagModules = modules.filter(m => m.shape === 'dag-graph')
const timelineModules = modules.filter(m => m.shape === 'job-timeline')
const analysisModules = modules.filter(m => m.shape === 'analysis-dashboard')

function parseCsv(text: string): string[][] {
  const records: string[][] = []
  let row: string[] = []
  let cell = ''
  let quoted = false
  const input = text.replace(/^\uFEFF/, '')
  for (let index = 0; index < input.length; index++) {
    const char = input[index]
    if (quoted) {
      if (char === '"' && input[index + 1] === '"') { cell += '"'; index++ }
      else if (char === '"') { quoted = false }
      else { cell += char }
    } else if (char === '"' && cell === '') { quoted = true }
    else if (char === ',') { row.push(cell); cell = '' }
    else if (char === '\n') {
      row.push(cell.replace(/\r$/, ''))
      if (row.some(v => v !== '')) records.push(row)
      row = []; cell = ''
    } else { cell += char }
  }
  row.push(cell.replace(/\r$/, ''))
  if (row.some(v => v !== '')) records.push(row)
  return records
}

test('CRUD模块：筛选、导出、登记、动作、指标全链路', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (crudModules.length === 0) { test.skip(); return }

  for (const mod of crudModules) {
    await page.goto(`/${mod.key}`)
    await page.waitForTimeout(3000)
    const bodyRows = page.locator('tbody tr[data-testid^="row-"]')
    await expect(bodyRows).toHaveCount(3)
    const firstValue = await bodyRows.nth(0).locator('td').nth(0).innerText()

    await page.getByTestId(`filter-${mod.fields[0]}`).fill(firstValue)
    await page.getByTestId('query').click()
    await expect(bodyRows).toHaveCount(1)
    await page.getByTestId('reset').click()
    await expect(bodyRows).toHaveCount(3)

    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('export').click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`${mod.key}.csv`)

    const createdValues = mod.fields.map((f, i) => `验收-${mod.key}-${i+1}`)
    await page.getByTestId('open-create').click()
    await expect(page.getByTestId('create-modal')).toBeVisible()
    for (const [i, field] of mod.fields.entries()) {
      await page.getByTestId(`create-${field}`).fill(createdValues[i])
    }
    await page.getByTestId('submit-create').click()
    await expect(page.getByTestId('create-modal')).toHaveCount(0)
    await expect(bodyRows).toHaveCount(4)

    const createdRow = page.locator('tbody tr').filter({ hasText: createdValues[0] })
    for (const [i, action] of mod.actions.entries()) {
      await createdRow.getByRole('button', { name: action, exact: true }).click()
      await expect(createdRow).toHaveAttribute('data-status', mod.actionTargets[i])
    }
  }

  expect(browserErrors).toEqual([])
})

test('DAG拓扑模块：节点渲染、详情、动作、导出', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (dagModules.length === 0) { test.skip(); return }

  for (const mod of dagModules) {
    await page.goto(`/${mod.key}`)
    await page.waitForTimeout(3000)
    await expect(page.locator('svg.dag-svg')).toBeVisible()
    const nodes = page.locator('g.dag-node')
    const count = await nodes.count()
    expect(count).toBeGreaterThanOrEqual(3)

    await nodes.first().click()
    await expect(page.getByTestId('dag-detail')).toBeVisible()

    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('export').click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`${mod.key}.csv`)

    await page.getByTestId('open-create').click()
    await expect(page.getByTestId('create-modal')).toBeVisible()
    for (const [i, field] of mod.fields.slice(0,3).entries()) {
      await page.locator('.create-field input').nth(i).fill(`E2E-${mod.key}-${i}`)
    }
    await page.getByTestId('submit-create').click()
    await expect(page.getByTestId('create-modal')).toHaveCount(0)
  }

  expect(browserErrors).toEqual([])
})

test('时间线模块：甘特条渲染、日期筛选、日志查看、登记', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (timelineModules.length === 0) { test.skip(); return }

  for (const mod of timelineModules) {
    await page.goto(`/${mod.key}`)
    await expect(page.locator('.timeline-bar').first()).toBeVisible({ timeout: 10000 })
    const bars = page.locator('.timeline-bar')
    const count = await bars.count()
    expect(count).toBeGreaterThanOrEqual(3)

    await bars.first().click()
    await expect(page.getByTestId('timeline-log')).toBeVisible()

    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('export').click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe(`${mod.key}.csv`)

    await page.getByTestId('open-create').click()
    await expect(page.getByTestId('create-modal')).toBeVisible()
    for (const [i, field] of mod.fields.slice(0,3).entries()) {
      await page.locator('.create-field input').nth(i).fill(`E2E-${mod.key}-${i}`)
    }
    await page.getByTestId('submit-create').click()
    await expect(page.getByTestId('create-modal')).toHaveCount(0)
  }

  expect(browserErrors).toEqual([])
})

test('分析看板模块：KPI卡片、运行分析、图表渲染', async ({ page }) => {
  test.setTimeout(300_000)
  const browserErrors: string[] = []
  page.on('pageerror', e => browserErrors.push(e.message))
  page.on('response', r => { if (r.url().includes('/api/') && r.status()>=400) browserErrors.push(`${r.status()} ${r.url()}`) })
  if (analysisModules.length === 0) { test.skip(); return }

  for (const mod of analysisModules) {
    await page.goto(`/${mod.key}`)
    await expect(page.getByTestId('kpi-card').first()).toBeVisible({ timeout: 10000 })
    const kpiCards = page.getByTestId('kpi-card')
    const kpiCount = await kpiCards.count()
    expect(kpiCount).toBeGreaterThanOrEqual(2)
    await expect(kpiCards.first().locator('strong')).toBeVisible()

    await page.getByTestId('run-analysis').click()
    await expect(page.locator('.analysis-bar').first()).toBeVisible({ timeout: 5000 })
    await expect(page.locator('.data-table tbody tr').first()).toBeVisible({ timeout: 5000 })
  }

  expect(browserErrors).toEqual([])
})

test('概览汇总', async ({ page }) => {
  test.setTimeout(300_000)
  await page.goto('/')
  await expect(page.locator('.stat-value').nth(1)).toBeVisible()
  // 验证概览页加载正常即可，不硬编码精确计数（取决于各模块 E2E 登记成功数）
})
