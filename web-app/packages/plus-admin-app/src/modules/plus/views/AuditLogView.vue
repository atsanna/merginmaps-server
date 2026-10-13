<!--
Copyright (C) 2026 merginmaps-server contributors

SPDX-License-Identifier: AGPL-3.0-only
-->

<template>
  <admin-layout>
    <app-container>
      <app-section ground>
        <template #header>
          <h1 class="headline-h3">
            Activity log
            <span class="text-color-medium-green">({{ count }})</span>
          </h1>
        </template>
      </app-section>
    </app-container>
    <app-container>
      <app-section ground>
        <form
          class="grid align-items-end"
          data-cy="audit-filters"
          @submit.prevent="applyFilters"
        >
          <span class="p-input-filled col-12 md:col-4 flex flex-column">
            <label for="audit-event-type" class="paragraph-p6 mb-1"
              >Event type</label
            >
            <PInputText
              id="audit-event-type"
              v-model="filters.eventType"
              placeholder="e.g. project.member"
              class="w-full"
            />
          </span>
          <span class="p-input-filled col-12 md:col-2 flex flex-column">
            <label for="audit-workspace" class="paragraph-p6 mb-1"
              >Workspace ID</label
            >
            <PInputNumber
              inputId="audit-workspace"
              v-model="filters.workspaceId"
              :useGrouping="false"
              :min="1"
              placeholder="Any"
              class="w-full"
            />
          </span>
          <span class="p-input-filled col-12 md:col-3 flex flex-column">
            <label for="audit-dates" class="paragraph-p6 mb-1"
              >Date range</label
            >
            <PCalendar
              inputId="audit-dates"
              v-model="filters.dates"
              selectionMode="range"
              :manualInput="false"
              showButtonBar
              dateFormat="yy-mm-dd"
              placeholder="Any time"
              class="w-full"
            />
          </span>
          <div class="col-12 md:col-3 flex gap-2 justify-content-end">
            <PButton severity="secondary" label="Clear" @click="clearFilters" />
            <PButton type="submit" icon="ti ti-filter" label="Filter" />
          </div>
        </form>
      </app-section>
    </app-container>
    <app-container>
      <app-section>
        <PDataTable
          :expandedRows="expandedRows"
          @update:expandedRows="expandedRows = $event"
          :value="items"
          dataKey="id"
          :lazy="true"
          :paginator="true"
          :rows="perPage"
          :rowsPerPageOptions="[20, 50, 100]"
          :totalRecords="count"
          :loading="loading"
          :first="(page - 1) * perPage"
          :rowHover="true"
          @page="onPage"
          data-cy="audit-table"
        >
          <PColumn expander style="width: 3rem" />
          <PColumn field="happened_at" header="Time">
            <template #body="{ data }">
              <span class="white-space-nowrap">{{
                dateUtils.formatDateTime(data.happened_at)
              }}</span>
            </template>
          </PColumn>
          <PColumn field="event_type" header="Event">
            <template #body="{ data }">
              <PTag severity="info" :value="data.event_type" />
            </template>
          </PColumn>
          <PColumn field="actor_email" header="Actor">
            <template #body="{ data }">
              <div class="flex flex-column">
                <span>{{ data.actor_email || '-' }}</span>
                <span v-if="data.actor_ip" class="paragraph-p6 opacity-80">{{
                  data.actor_ip
                }}</span>
              </div>
            </template>
          </PColumn>
          <PColumn header="Target">
            <template #body="{ data }">
              <div class="flex flex-column paragraph-p6">
                <span v-if="data.target_workspace_id"
                  >Workspace:
                  <router-link
                    :to="{
                      name: PlusAdminRoutes.WORKSPACE,
                      params: { id: data.target_workspace_id }
                    }"
                    >{{ data.target_workspace_id }}</router-link
                  ></span
                >
                <span v-if="data.target_project_id"
                  >Project: {{ data.target_project_id }}</span
                >
                <span v-if="data.target_user_id"
                  >User ID: {{ data.target_user_id }}</span
                >
                <span
                  v-if="
                    !data.target_workspace_id &&
                    !data.target_project_id &&
                    !data.target_user_id
                  "
                  >-</span
                >
              </div>
            </template>
          </PColumn>
          <PColumn header="Details">
            <template #body="{ data }">
              <code
                class="paragraph-p6 block overflow-hidden text-overflow-ellipsis white-space-nowrap"
                style="max-width: 320px"
                :title="compactJson(data.metadata)"
                >{{ compactJson(data.metadata) }}</code
              >
            </template>
          </PColumn>
          <template #expansion="{ data }">
            <pre
              class="paragraph-p6 m-0 p-3 surface-ground border-round-lg overflow-auto"
              >{{ prettyJson(data.metadata) }}</pre
            >
          </template>
          <template #empty>
            <p class="paragraph-p5 text-center p-4">No events found.</p>
          </template>
          <template #paginatorstart>
            <PButton
              icon="ti ti-refresh"
              plain
              text
              rounded
              @click="fetchEvents"
            />
          </template>
          <template #paginatorend />
        </PDataTable>
      </app-section>
    </app-container>
  </admin-layout>
</template>

<script setup lang="ts">
import { AdminLayout } from '@mergin/admin-lib'
import {
  AppContainer,
  AppSection,
  dateUtils,
  errorUtils,
  useNotificationStore
} from '@mergin/lib'
import axios from 'axios'
import { DataTableExpandedRows, DataTablePageEvent } from 'primevue/datatable'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { PlusAdminApi } from '../api'
import { PlusAdminRoutes } from '../routes'
import { AuditEvent, AuditParams } from '../types'

const route = useRoute()
const router = useRouter()
const notificationStore = useNotificationStore()

const items = ref<AuditEvent[]>([])
const count = ref(0)
const loading = ref(false)
const page = ref(1)
const perPage = ref(50)
const expandedRows = ref<AuditEvent[] | DataTableExpandedRows>([])
let abortController: AbortController | null = null

const filters = reactive<{
  eventType: string
  workspaceId: number | null
  dates: Date[] | null
}>({
  eventType: '',
  workspaceId: null,
  dates: null
})

const toIsoDate = (value: Date) =>
  `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(
    2,
    '0'
  )}-${String(value.getDate()).padStart(2, '0')}`

const fromIsoDate = (value: unknown): Date | null => {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value))
    return null
  const [year, month, day] = value.split('-').map(Number)
  return new Date(year, month - 1, day)
}

/** Inclusive start of the selected range (local midnight) */
const rangeSince = (): Date | null => filters.dates?.[0] ?? null

/** Exclusive end of the selected range (midnight after the last selected day) */
const rangeUntil = (): Date | null => {
  const last = filters.dates?.[1] ?? filters.dates?.[0]
  if (!last) return null
  const until = new Date(last)
  until.setDate(until.getDate() + 1)
  return until
}

const compactJson = (value: unknown) =>
  value && Object.keys(value).length ? JSON.stringify(value) : '-'

const prettyJson = (value: unknown) =>
  value ? JSON.stringify(value, null, 2) : 'No details'

const initFromQuery = () => {
  const q = route.query
  if (q.event_type) filters.eventType = String(q.event_type)
  if (q.workspace_id && !isNaN(Number(q.workspace_id)))
    filters.workspaceId = Number(q.workspace_id)
  const since = fromIsoDate(q.since)
  const until = fromIsoDate(q.until)
  if (since) filters.dates = until ? [since, until] : [since]
  if (q.page) page.value = Number(q.page) || 1
  if (q.per_page) perPage.value = Number(q.per_page) || 50
}

const updateQuery = () => {
  const query: Record<string, string> = {}
  if (filters.eventType.trim()) query.event_type = filters.eventType.trim()
  if (filters.workspaceId) query.workspace_id = String(filters.workspaceId)
  if (filters.dates?.[0]) query.since = toIsoDate(filters.dates[0])
  if (filters.dates?.[1]) query.until = toIsoDate(filters.dates[1])
  if (page.value > 1) query.page = String(page.value)
  if (perPage.value !== 50) query.per_page = String(perPage.value)
  router.replace({ query })
}

const fetchEvents = async () => {
  abortController?.abort()
  abortController = new AbortController()
  updateQuery()
  const params: AuditParams = { page: page.value, per_page: perPage.value }
  if (filters.eventType.trim()) params.event_type = filters.eventType.trim()
  if (filters.workspaceId) params.workspace_id = filters.workspaceId
  const since = rangeSince()
  const until = rangeUntil()
  if (since) params.since = since.toISOString()
  if (until) params.until = until.toISOString()
  loading.value = true
  try {
    const response = await PlusAdminApi.fetchAuditEvents(
      params,
      abortController.signal
    )
    items.value = response.data.items
    count.value = response.data.count
    expandedRows.value = []
    loading.value = false
  } catch (err) {
    if (axios.isCancel(err)) return
    loading.value = false
    notificationStore.error({
      text: errorUtils.getErrorMessage(err, 'Failed to load activity log')
    })
  }
}

const applyFilters = () => {
  page.value = 1
  fetchEvents()
}

const clearFilters = () => {
  filters.eventType = ''
  filters.workspaceId = null
  filters.dates = null
  applyFilters()
}

const onPage = (event: DataTablePageEvent) => {
  page.value = event.page + 1
  perPage.value = event.rows
  fetchEvents()
}

initFromQuery()
fetchEvents()
</script>
