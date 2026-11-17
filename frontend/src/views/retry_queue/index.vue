<template>
  <section class="page" data-module="retry_queue">
    <header class="page-head">
      <div><h2>重试队列</h2><p class="page-desc">维护采集失败页面的重试队列、退避时间与终态处理，保障采集完整性。</p></div>
      <div class="page-actions">
        <button class="btn primary" type="button" data-testid="open-create" @click="openCreate">登记重试条目</button>
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
    </div>

    <!-- 失败窗口续做：与定时调度共用唯一续做入口 -->
    <section class="resume-panel" data-testid="resume-panel">
      <header class="resume-head">
        <div>
          <h3>失败窗口续做</h3>
          <p class="page-desc">重试队列接收失败窗口；续做只会补建任务批次，不覆盖上一轮已完成的采集任务。</p>
        </div>
        <button class="btn" type="button" data-testid="reload-resume" @click="loadResumeEntries">刷新待续做</button>
      </header>
      <p v-if="resumeMessage" class="resume-message" data-testid="resume-message">{{ resumeMessage }}</p>
      <p v-if="errorMessage" class="error-text" data-testid="resume-error">{{ errorMessage }}</p>
      <table class="data-table">
        <thead>
          <tr><th>重试条目</th><th>调度计划</th><th>窗口起始</th><th>重试状态</th><th>触发记录</th><th>续做批次</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in resumeEntries" :key="row.id" :data-testid="`resume-${row.id}`">
            <td>{{ row['条目编号'] }}</td>
            <td>{{ row['计划编号'] || '—' }}</td>
            <td>{{ row['窗口起始'] || '—' }}</td>
            <td>{{ row.status }}</td>
            <td>{{ row['触发记录'] ? `#${row['触发记录']}` : '—' }}</td>
            <td>{{ batchLabel(row) }}</td>
            <td>
              <button class="btn" type="button" data-testid="resume-entry" :disabled="resuming || row.status === '已恢复'" @click="resumeEntry(row)">
                {{ row.status === '已恢复' ? '已续做' : '续做' }}
              </button>
            </td>
          </tr>
          <tr v-if="!resumeEntries.length"><td colspan="7" class="empty-state">暂无关联调度窗口的重试条目</td></tr>
        </tbody>
      </table>
    </section>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate"><h3>登记重试条目</h3>
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
import { onMounted, ref } from 'vue'
import { request } from '@/api/client'
const ENDPOINT = '/api/retry_queue'
const columns = ["条目编号", "失败页面", "失败原因", "重试次数", "最大重试", "下次重试", "错误详情", "关联任务"]
const actions = ["强制重试", "标记放弃", "确认恢复"]
const timelineItems = ref<any[]>([])
const selectedItem = ref<any>(null)
const dateFrom = ref(''); const dateTo = ref('')
const errorMessage = ref(''); const showCreate = ref(false)
const createValues = ref<Record<string,string>>({})
const allItems = ref<any[]>([])
const resumeEntries = ref<any[]>([])
const resuming = ref(false)
const resumeMessage = ref('')
function barLeft(item: any) { const all = allItems.value.filter(i => i.start && i.end); if(!all.length) return 0; const min = Math.min(...all.map(i => new Date(i.start).getTime())); const max = Math.max(...all.map(i => new Date(i.end).getTime())); const range = max - min || 86400000; return ((new Date(item.start).getTime() - min) / range) * 100 }
function barWidth(item: any) { const all = allItems.value.filter(i => i.start && i.end); if(!all.length) return 20; const min = Math.min(...all.map(i => new Date(i.start).getTime())); const max = Math.max(...all.map(i => new Date(i.end).getTime())); const range = max - min || 86400000; return Math.max(5, ((new Date(item.end).getTime() - new Date(item.start).getTime()) / range) * 100) }
function selectItem(item: any) { selectedItem.value = selectedItem.value?.id === item.id ? null : item }
function batchLabel(row: any) {
  if(row.resume_batch_id) return `#${row.resume_batch_id} ${row.resume_status || ''}`
  return row.resume_status || '待生成'
}
async function reload() {
  try { const res = await request(ENDPOINT); const data = await res.json(); allItems.value = data.items || []; applyFilter() } catch(e) { errorMessage.value = '加载失败' }
}
function applyFilter() {
  let items = allItems.value
  if(dateFrom.value) items = items.filter((i: any) => i.start >= dateFrom.value)
  if(dateTo.value) items = items.filter((i: any) => i.end <= dateTo.value)
  timelineItems.value = items; selectedItem.value = null
}
async function loadResumeEntries() {
  try {
    const entryRes = await request(`${ENDPOINT}/joint/windows`)
    if(!entryRes.ok) throw new Error('待续做条目加载失败')
    const entryData = await entryRes.json()
    resumeEntries.value = entryData.items || []
  } catch(e: any) { errorMessage.value = e.message }
}
async function resumeEntry(row: any) {
  resuming.value = true; errorMessage.value = ''
  try {
    const res = await request(`${ENDPOINT}/${row.id}/resume`, { method: 'POST', body: JSON.stringify({}) })
    const data = await res.json()
    if(!res.ok || data.ok === false) throw new Error(data.detail || data.error || '续做失败')
    resumeMessage.value = data.message || '续做任务批次已生成'
    await Promise.all([loadResumeEntries(), reload()])
  } catch(e: any) { errorMessage.value = e.message } finally { resuming.value = false }
}
function openCreate() { createValues.value = {}; showCreate.value = true }
async function submitCreate() {
  try { const res = await request(ENDPOINT, { method: 'POST', body: JSON.stringify({ values: createValues.value }) }); if(!res.ok) throw new Error('创建失败'); showCreate.value = false; await reload() } catch(e: any) { errorMessage.value = e.message }
}
function exportRows() { window.open(`${ENDPOINT}/export`, '_blank') }
onMounted(() => { reload(); loadResumeEntries() })
</script>
<style scoped>
.resume-panel { margin-top: 16px; background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
.resume-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.resume-head h3 { margin: 0 0 4px; font-size: 15px; }
.resume-message { font-size: 12px; color: #1f6feb; margin: 8px 0; }
</style>
