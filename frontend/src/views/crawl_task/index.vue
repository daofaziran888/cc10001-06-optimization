<template>
  <section class="page" data-module="crawl_task">
    <header class="page-head">
      <div><h2>采集任务</h2><p class="page-desc">维护采集任务的定义、调度、优先级与截止约束，驱动批量爬取执行。</p></div>
      <div class="page-actions">
        <button class="btn primary" type="button" data-testid="open-create" @click="openCreate">登记任务批次</button>
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

    <!-- 续做任务批次：与定时调度、重试队列同步的窗口清单 -->
    <section class="resume-batch-panel" data-testid="resume-batch-panel">
      <header class="resume-batch-head">
        <div>
          <h3>续做任务批次</h3>
          <p class="page-desc">失败窗口经唯一续做入口补建的任务批次；同一窗口不会覆盖上一轮已完成任务。</p>
        </div>
        <button class="btn" type="button" data-testid="reload-resume-batches" @click="loadResumeBatches">刷新批次</button>
      </header>
      <table class="data-table">
        <thead>
          <tr><th>批次</th><th>计划编号</th><th>窗口起始</th><th>状态</th><th>失败任务</th><th>续做任务</th><th>重试条目</th></tr>
        </thead>
        <tbody>
          <tr v-for="batch in resumeBatches" :key="batch.id" :data-testid="`resume-batch-${batch.id}`">
            <td>#{{ batch.id }}</td>
            <td>{{ batch.plan_code }}</td>
            <td>{{ batch.window_start }}</td>
            <td>{{ batch.status }}</td>
            <td>{{ batch.failed_task_id ? `#${batch.failed_task_id}` : '—' }}</td>
            <td>{{ batch.task_id ? `#${batch.task_id}` : '—' }}</td>
            <td>{{ batch.retry_entry_id ? `#${batch.retry_entry_id}` : '—' }}</td>
          </tr>
          <tr v-if="!resumeBatches.length"><td colspan="7" class="empty-state">暂无续做任务批次</td></tr>
        </tbody>
      </table>
    </section>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate"><h3>登记任务批次</h3>
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
const ENDPOINT = '/api/crawl_task'
const columns = ["任务编号", "目标站点", "入口URL", "深度限制", "页面上限", "调度cron", "优先级", "截止时间"]
const actions = ["提交调度", "取消任务", "归档结果"]
const timelineItems = ref<any[]>([])
const selectedItem = ref<any>(null)
const dateFrom = ref(''); const dateTo = ref('')
const errorMessage = ref(''); const showCreate = ref(false)
const createValues = ref<Record<string,string>>({})
const allItems = ref<any[]>([])
const resumeBatches = ref<any[]>([])
function barLeft(item: any) { const all = allItems.value.filter(i => i.start && i.end); if(!all.length) return 0; const min = Math.min(...all.map(i => new Date(i.start).getTime())); const max = Math.max(...all.map(i => new Date(i.end).getTime())); const range = max - min || 86400000; return ((new Date(item.start).getTime() - min) / range) * 100 }
function barWidth(item: any) { const all = allItems.value.filter(i => i.start && i.end); if(!all.length) return 20; const min = Math.min(...all.map(i => new Date(i.start).getTime())); const max = Math.max(...all.map(i => new Date(i.end).getTime())); const range = max - min || 86400000; return Math.max(5, ((new Date(item.end).getTime() - new Date(item.start).getTime()) / range) * 100) }
function selectItem(item: any) { selectedItem.value = selectedItem.value?.id === item.id ? null : item }
async function reload() {
  try { const res = await request(ENDPOINT); const data = await res.json(); allItems.value = data.items || []; applyFilter() } catch(e) { errorMessage.value = '加载失败' }
}
async function loadResumeBatches() {
  try { const res = await request('/api/scheduler/joint/resume-batches'); if(!res.ok) throw new Error('批次加载失败'); resumeBatches.value = await res.json() } catch(e: any) { errorMessage.value = e.message }
}
function applyFilter() {
  let items = allItems.value
  if(dateFrom.value) items = items.filter((i: any) => i.start >= dateFrom.value)
  if(dateTo.value) items = items.filter((i: any) => i.end <= dateTo.value)
  timelineItems.value = items; selectedItem.value = null
}
function openCreate() { createValues.value = {}; showCreate.value = true }
async function submitCreate() {
  try { const res = await request(ENDPOINT, { method: 'POST', body: JSON.stringify({ values: createValues.value }) }); if(!res.ok) throw new Error('创建失败'); showCreate.value = false; await reload() } catch(e: any) { errorMessage.value = e.message }
}
function exportRows() { window.open(`${ENDPOINT}/export`, '_blank') }
onMounted(() => { reload(); loadResumeBatches() })
</script>
<style scoped>
.resume-batch-panel { margin-top: 16px; background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 14px; }
.resume-batch-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.resume-batch-head h3 { margin: 0 0 4px; font-size: 15px; }
</style>
