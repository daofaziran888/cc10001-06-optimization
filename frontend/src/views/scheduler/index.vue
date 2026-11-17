<template>
  <section class="page" data-module="scheduler">
    <header class="page-head">
      <div><h2>定时调度</h2><p class="page-desc">维护采集任务的定时调度计划、重试策略与失败通知，保障采集周期稳定执行。</p></div>
      <div class="page-actions">
        <button class="btn primary" type="button" data-testid="open-create" @click="openCreate">登记调度计划</button>
        <button class="btn" type="button" data-testid="export" @click="exportRows">导出作业清单</button>
      </div>
    </header>
    <div class="filter-bar">
      <label><span>开始日期</span><input type="date" v-model="dateFrom" /></label>
      <label><span>结束日期</span><input type="date" v-model="dateTo" /></label>
      <button class="btn" type="button" @click="reload">查询</button>
    </div>
    <div class="timeline-wrap">
      <div v-for="item in timelineItems" :key="item.id" class="timeline-row">
        <span class="timeline-label">{{ item.name || item.label }}</span>
        <div class="timeline-track">
          <div class="timeline-bar" :class="`status-${item.status}`" :style="{ left: barLeft(item) + '%', width: barWidth(item) + '%' }" :data-testid="`bar-${item.id}`" :title="`${item.start} ~ ${item.end}`" @click="selectItem(item)">&nbsp;</div>
        </div>
        <span style="font-size:12px;color:var(--muted);margin-left:8px;">{{ item.start }} ~ {{ item.end }}</span>
      </div>
      <p v-if="!timelineItems.length" style="text-align:center;color:var(--muted)">暂无作业记录</p>
    </div>
    <div v-if="selectedItem" class="timeline-log" data-testid="timeline-log">
      <strong>{{ selectedItem.name || selectedItem.label }}</strong> — 状态：{{ selectedItem.status }}
      <div style="margin-top:4px;">{{ selectedItem.logs || '暂无日志' }}</div>
      <div v-if="selectedItem.next_run" style="margin-top:4px;">下次执行：{{ selectedItem.next_run }}</div>
    </div>

    <!-- 批量扫描：读取触发记录 + 续做批次，按窗口区分新触发 / 已跳过 / 待续做 -->
    <section class="scan-panel" data-testid="scan-panel">
      <header class="scan-head">
        <div>
          <h3>批量调度扫描</h3>
          <p class="scan-desc">扫描待激活计划与失败窗口。成功窗口只标记已跳过，失败窗口进入重试队列并生成续做批次，续做只走一个入口。</p>
        </div>
        <div class="scan-actions">
          <label class="scan-scope"><span>扫描范围</span>
            <select v-model="scope" data-testid="scan-scope">
              <option v-for="option in scopes" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label class="scan-toggle"><input type="checkbox" v-model="simulateFailure" data-testid="scan-simulate-failure" />模拟失败窗口</label>
          <button class="btn primary" type="button" data-testid="scan-run" :disabled="scanning" @click="runScan">{{ scanning ? '扫描中…' : '执行批量扫描' }}</button>
        </div>
      </header>
      <p v-if="scanMessage" class="scan-message" data-testid="scan-message">{{ scanMessage }}</p>
      <p v-if="errorMessage" class="error-text" data-testid="scan-error">{{ errorMessage }}</p>
      <div class="stat-row">
        <article v-for="chip in summaryChips" :key="chip.key" class="stat-card" data-testid="scan-summary">
          <span class="stat-label">{{ chip.key }}</span>
          <strong class="stat-value">{{ chip.value }}</strong>
        </article>
      </div>
      <table class="data-table scan-table">
        <thead>
          <tr><th>计划编号</th><th>窗口起始</th><th>窗口分类</th><th>触发记录</th><th>重试条目</th><th>续做批次</th><th>说明</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in windows" :key="row.window_key" :data-testid="`window-${row.window_key}`" :data-classification="row.classification">
            <td>{{ row.plan_code }}</td>
            <td>{{ row.window_start }}</td>
            <td><span class="window-tag" :class="`window-${row.classification}`">{{ row.classification }}</span></td>
            <td>{{ row.trigger_id ? `#${row.trigger_id} ${row.trigger_status}` : '—' }}</td>
            <td>{{ row.retry_entry_id ? `#${row.retry_entry_id} ${row.retry_status || ''}` : '—' }}</td>
            <td>{{ row.resume_batch_id ? `#${row.resume_batch_id} ${row.resume_status || ''}` : '—' }}</td>
            <td class="scan-note">{{ row.last_scanned_at ? `最近扫描：${row.last_scanned_at}` : '尚未扫描' }}</td>
            <td>
              <button v-if="row.classification === '待续做' && row.trigger_id" class="btn" type="button" data-testid="resume-window" :disabled="resuming" @click="resumeWindow(row)">续做</button>
              <span v-else class="scan-note">{{ row.classification === '已跳过' ? '已成功，跳过' : '—' }}</span>
            </td>
          </tr>
          <tr v-if="!windows.length"><td colspan="8" class="empty-state">暂无调度窗口</td></tr>
        </tbody>
      </table>
      <p v-if="lastScanResults.length" class="scan-desc" data-testid="scan-results">
        最近一次扫描：{{ lastScanResults.map((item: any) => `${item.window_start} ${item.classification}`).join('；') }}
      </p>
    </section>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate"><h3>登记调度计划</h3>
        <label v-for="field in columns.slice(0,3)" :key="field" class="create-field"><span>{{ field }}</span><input v-model="createValues[field]" :placeholder="`请输入${field}`" required /></label>
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px">
          <button class="btn" type="button" @click="showCreate=false">取消</button>
          <button class="btn primary" type="submit" data-testid="submit-create">提交</button>
        </div>
      </form>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { request } from '@/api/client'
const ENDPOINT = '/api/scheduler'
const columns = ["计划编号", "关联任务", "Cron表达式", "时区", "重试次数", "失败通知", "并发上限", "下次执行"]
const actions = ["激活计划", "立即执行", "停用计划"]
const timelineItems = ref<any[]>([])
const selectedItem = ref<any>(null)
const dateFrom = ref(''); const dateTo = ref('')
const errorMessage = ref(''); const showCreate = ref(false)
const createValues = ref<Record<string,string>>({})
const allItems = ref<any[]>([])
// 扫描范围：决定刚到期的新窗口本轮进入采集，还是下一轮才进入
const scopes = ref<{ value: string, label: string }[]>([
  { value: 'include_due', label: '本轮纳入刚到期窗口' },
  { value: 'defer_due', label: '下一轮再纳入刚到期窗口' },
])
const scope = ref('include_due')
const simulateFailure = ref(false)
const scanning = ref(false); const resuming = ref(false)
const scanMessage = ref('')
const windows = ref<any[]>([])
const scanSummary = ref<Record<string, number>>({})
const lastScanResults = ref<any[]>([])
const summaryKeys = ['新触发', '已跳过', '待续做', '已续做', '待下一轮', '未到期', '待触发']
const summaryChips = computed(() => summaryKeys.map(key => ({ key, value: scanSummary.value[key] ?? 0 })))
function barLeft(item: any) { const all = allItems.value.filter(i => i.start && i.end); if(!all.length) return 0; const min = Math.min(...all.map(i => new Date(i.start).getTime())); const max = Math.max(...all.map(i => new Date(i.end).getTime())); const range = max - min || 86400000; return ((new Date(item.start).getTime() - min) / range) * 100 }
function barWidth(item: any) { const all = allItems.value.filter(i => i.start && i.end); if(!all.length) return 20; const min = Math.min(...all.map(i => new Date(i.start).getTime())); const max = Math.max(...all.map(i => new Date(i.end).getTime())); const range = max - min || 86400000; return Math.max(5, ((new Date(item.end).getTime() - new Date(item.start).getTime()) / range) * 100) }
function selectItem(item: any) { selectedItem.value = selectedItem.value?.id === item.id ? null : item }
async function reload() {
  try { const res = await request(ENDPOINT); const data = await res.json(); allItems.value = data.items || []; applyFilter() } catch(e) { errorMessage.value = '加载失败' }
}
function applyFilter() {
  let items = allItems.value
  if(dateFrom.value) items = items.filter((i: any) => i.start >= dateFrom.value)
  if(dateTo.value) items = items.filter((i: any) => i.end <= dateTo.value)
  timelineItems.value = items; selectedItem.value = null
}
async function loadWindows() {
  try {
    const res = await request(`${ENDPOINT}/windows`)
    if(!res.ok) throw new Error('窗口加载失败')
    const data = await res.json()
    windows.value = data.items || []
    scanSummary.value = data.summary || {}
    if(Array.isArray(data.scopes) && data.scopes.length) scopes.value = data.scopes
  } catch(e: any) { errorMessage.value = e.message }
}
async function runScan() {
  scanning.value = true; errorMessage.value = ''
  try {
    const res = await request(`${ENDPOINT}/scan`, {
      method: 'POST',
      body: JSON.stringify({ scope: scope.value, simulate_failure: simulateFailure.value }),
    })
    const data = await res.json()
    if(!res.ok || data.ok === false) throw new Error(data.detail || data.error || '扫描失败')
    scanSummary.value = data.summary || {}
    lastScanResults.value = data.results || []
    scanMessage.value = `扫描完成：${data.scope_label}，共扫描 ${data.scanned} 个计划`
    await Promise.all([loadWindows(), reload()])
  } catch(e: any) { errorMessage.value = e.message } finally { scanning.value = false }
}
async function resumeWindow(row: any) {
  if(!row.trigger_id) return
  resuming.value = true; errorMessage.value = ''
  try {
    const res = await request(`${ENDPOINT}/resume`, {
      method: 'POST',
      body: JSON.stringify({ trigger_id: row.trigger_id }),
    })
    const data = await res.json()
    if(!res.ok || data.ok === false) throw new Error(data.detail || data.error || '续做失败')
    scanMessage.value = data.message || '失败窗口已续做'
    await loadWindows()
  } catch(e: any) { errorMessage.value = e.message } finally { resuming.value = false }
}
function openCreate() { createValues.value = {}; showCreate.value = true }
async function submitCreate() {
  try { const res = await request(ENDPOINT, { method: 'POST', body: JSON.stringify({ values: createValues.value }) }); if(!res.ok) throw new Error('创建失败'); showCreate.value = false; await reload() } catch(e: any) { errorMessage.value = e.message }
}
function exportRows() { window.open(`${ENDPOINT}/export`, '_blank') }
onMounted(() => { reload(); loadWindows() })
</script>
<style scoped>
.scan-panel { margin-top: 16px; background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
.scan-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
.scan-head h3 { margin: 0 0 4px; font-size: 15px; }
.scan-desc { color: var(--muted); font-size: 12px; margin: 0 0 10px; }
.scan-actions { display: flex; align-items: flex-end; gap: 12px; flex-wrap: wrap; }
.scan-scope { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.scan-scope select { padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; }
.scan-toggle { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--muted); }
.scan-message { font-size: 12px; color: #1f6feb; margin: 0 0 8px; }
.scan-table td { vertical-align: middle; }
.scan-note { color: var(--muted); font-size: 12px; }
.window-tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; background: #eef2f7; color: #334155; }
.window-tag.window-新触发 { background: #dbeafe; color: #1d4ed8; }
.window-tag.window-已跳过 { background: #dcfce7; color: #15803d; }
.window-tag.window-待续做 { background: #fee2e2; color: #b91c1c; }
.window-tag.window-已续做 { background: #ede9fe; color: #6d28d9; }
.window-tag.window-待下一轮,
.window-tag.window-待触发 { background: #fef3c7; color: #b45309; }
</style>
