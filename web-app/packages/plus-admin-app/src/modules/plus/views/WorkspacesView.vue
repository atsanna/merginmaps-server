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
            Workspaces
            <span class="text-color-medium-green">({{ count }})</span>
          </h1>
        </template>
        <template #headerActions>
          <PButton
            icon="ti ti-plus"
            label="Create workspace"
            data-cy="create-workspace-btn"
            @click="openCreateDialog"
          />
        </template>
      </app-section>
    </app-container>
    <app-container>
      <app-section ground>
        <span class="p-input-icon-left w-full">
          <i class="ti ti-search paragraph-p3"></i>
          <PInputText
            placeholder="Search workspaces"
            data-cy="search-workspaces-field"
            v-model="search"
            class="w-full"
            @input="onSearch"
          />
        </span>
      </app-section>
    </app-container>
    <app-container>
      <app-section>
        <PDataTable
          :value="items"
          :lazy="true"
          :paginator="true"
          :rows="options.itemsPerPage"
          :rowsPerPageOptions="options.perPageOptions"
          :totalRecords="count"
          :loading="loading"
          :first="(options.page - 1) * options.itemsPerPage"
          :sort-field="options.sortBy[0]"
          :sort-order="options.sortDesc[0] ? -1 : 1"
          :rowHover="true"
          removableSort
          @page="onPage"
          @sort="onSort"
          data-cy="workspaces-table"
        >
          <PColumn field="name" header="Name" sortable>
            <template #body="{ data }">
              <router-link
                :to="workspaceRoute(data)"
                class="dt-row-link title-t4"
                >{{ data.name }}</router-link
              >
            </template>
          </PColumn>
          <PColumn field="storage" header="Storage" sortable>
            <template #body="{ data }">
              <router-link :to="workspaceRoute(data)" class="dt-row-link">
                <div class="flex flex-column row-gap-1">
                  <span
                    >{{ formatBytes(data.disk_usage) }} /
                    {{ formatBytes(data.storage) }}</span
                  >
                  <PProgressBar
                    :value="usagePercent(data.disk_usage, data.storage)"
                    :showValue="false"
                    style="height: 4px"
                  />
                </div>
              </router-link>
            </template>
          </PColumn>
          <PColumn field="contributors" header="Contributors">
            <template #body="{ data }">
              <router-link :to="workspaceRoute(data)" class="dt-row-link">
                {{ data.contributors_count }} /
                {{ data.contributors_limit ?? '∞' }}
              </router-link>
            </template>
          </PColumn>
          <PColumn field="members_count" header="Members">
            <template #body="{ data }">
              <router-link :to="workspaceRoute(data)" class="dt-row-link">{{
                data.members_count
              }}</router-link>
            </template>
          </PColumn>
          <PColumn field="project_count" header="Projects">
            <template #body="{ data }">
              <router-link :to="workspaceRoute(data)" class="dt-row-link">{{
                data.project_count
              }}</router-link>
            </template>
          </PColumn>
          <PColumn field="created" header="Created" sortable>
            <template #body="{ data }">
              <router-link :to="workspaceRoute(data)" class="dt-row-link">{{
                dateUtils.formatDate(data.created)
              }}</router-link>
            </template>
          </PColumn>
          <PColumn field="active" header="Status" sortable>
            <template #body="{ data }">
              <router-link :to="workspaceRoute(data)" class="dt-row-link">
                <workspace-status-tag :workspace="data" />
              </router-link>
            </template>
          </PColumn>
          <template #empty>
            <p class="paragraph-p5 text-center p-4">No workspaces found.</p>
          </template>
          <template #paginatorstart>
            <PButton
              icon="ti ti-refresh"
              plain
              text
              rounded
              @click="onRefresh"
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
  useDataTableSearch,
  useDialogStore,
  useNotificationStore
} from '@mergin/lib'
import axios from 'axios'
import { ref } from 'vue'

import { PlusAdminApi } from '../api'
import CreateWorkspaceForm from '../components/CreateWorkspaceForm.vue'
import WorkspaceStatusTag from '../components/WorkspaceStatusTag.vue'
import { PlusAdminRoutes } from '../routes'
import { AdminWorkspace, AdminWorkspacesParams } from '../types'
import { formatBytes, usagePercent } from '../utils'

const dialogStore = useDialogStore()
const notificationStore = useNotificationStore()

const items = ref<AdminWorkspace[]>([])
const count = ref(0)
const loading = ref(false)

const {
  search,
  options,
  setFetchFn,
  initFromQuery,
  doFetch,
  onSearch,
  onPage,
  onSort,
  onRefresh
} = useDataTableSearch({ defaultSortBy: 'name', defaultSortDesc: false })

setFetchFn(async (signal) => {
  const params: AdminWorkspacesParams = {
    page: options.page,
    per_page: options.itemsPerPage
  }
  if (options.sortBy[0]) {
    params.order_params = `${options.sortBy[0]} ${
      options.sortDesc[0] ? 'DESC' : 'ASC'
    }`
  }
  if (search.value) params.like = search.value.trim()
  loading.value = true
  try {
    const response = await PlusAdminApi.fetchWorkspaces(params, signal)
    items.value = response.data.items
    count.value = response.data.count
    loading.value = false
  } catch (err) {
    if (axios.isCancel(err)) return
    loading.value = false
    notificationStore.error({
      text: errorUtils.getErrorMessage(err, 'Failed to load workspaces')
    })
  }
})

initFromQuery()
doFetch()

const workspaceRoute = (data: AdminWorkspace) => ({
  name: PlusAdminRoutes.WORKSPACE,
  params: { id: data.id }
})

const openCreateDialog = () => {
  dialogStore.show({
    component: CreateWorkspaceForm,
    params: {
      dialog: { maxWidth: 500, header: 'Create workspace' },
      listeners: {
        success: () => {
          options.page = 1
          doFetch()
        }
      }
    }
  })
}
</script>
