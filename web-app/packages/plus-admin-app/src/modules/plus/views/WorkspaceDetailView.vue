<!--
Copyright (C) 2026 merginmaps-server contributors

SPDX-License-Identifier: AGPL-3.0-only
-->

<template>
  <admin-layout>
    <app-container>
      <app-section ground>
        <template #header>
          <h1 class="headline-h3">Workspace details</h1>
        </template>
        <template #headerActions>
          <PButton
            v-if="workspace"
            severity="secondary"
            icon="ti ti-history"
            label="Activity log"
            @click="openActivityLog"
          />
        </template>
      </app-section>
    </app-container>

    <PProgressBar
      v-if="loading && !workspace"
      mode="indeterminate"
      style="height: 4px"
    />

    <template v-if="workspace">
      <app-container>
        <app-section class="p-4">
          <div class="flex flex-column row-gap-3">
            <div class="flex align-items-center gap-2 flex-wrap">
              <h2 class="headline-h2" data-cy="workspace-name">
                {{ workspace.name }}
              </h2>
              <workspace-status-tag :workspace="workspace" />
            </div>
            <dl class="paragraph-p5 grid m-0">
              <div class="col-12 md:col-4">
                <dt class="paragraph-p6 opacity-80">Workspace ID</dt>
                <dd class="font-semibold m-0">{{ workspace.id }}</dd>
              </div>
              <div class="col-12 md:col-4">
                <dt class="paragraph-p6 opacity-80">Created</dt>
                <dd class="font-semibold m-0">
                  {{ dateUtils.formatDate(workspace.created) }}
                </dd>
              </div>
              <div class="col-12 md:col-4">
                <dt class="paragraph-p6 opacity-80">Projects</dt>
                <dd class="font-semibold m-0">
                  {{ workspace.project_count }}
                </dd>
              </div>
              <div class="col-12 md:col-4">
                <dt class="paragraph-p6 opacity-80">Storage used</dt>
                <dd class="font-semibold m-0">
                  {{ formatBytes(workspace.disk_usage) }} /
                  {{ formatBytes(workspace.storage) }}
                  <PProgressBar
                    :value="
                      usagePercent(workspace.disk_usage, workspace.storage)
                    "
                    :showValue="false"
                    class="mt-1"
                    style="height: 4px; max-width: 240px"
                  />
                </dd>
              </div>
              <div class="col-12 md:col-4">
                <dt class="paragraph-p6 opacity-80">Contributors</dt>
                <dd class="font-semibold m-0">
                  {{ workspace.contributors_count }} /
                  {{ workspace.contributors_limit ?? 'unlimited' }}
                </dd>
              </div>
              <div class="col-12 md:col-4">
                <dt class="paragraph-p6 opacity-80">Members</dt>
                <dd class="font-semibold m-0">
                  {{ workspace.members_count }}
                </dd>
              </div>
              <div v-if="workspace.removed_at" class="col-12 md:col-4">
                <dt class="paragraph-p6 opacity-80">Removal requested</dt>
                <dd class="font-semibold m-0">
                  {{ dateUtils.formatDateTime(workspace.removed_at) }}
                </dd>
              </div>
              <div v-if="workspace.expiration" class="col-12 md:col-4">
                <dt class="paragraph-p6 opacity-80">Permanent removal</dt>
                <dd class="font-semibold m-0">
                  {{ dateUtils.formatDateTime(workspace.expiration) }}
                </dd>
              </div>
            </dl>
          </div>
        </app-section>
      </app-container>

      <app-container>
        <app-section>
          <template #title>Limits and description</template>
          <form
            class="flex flex-column row-gap-3 px-4 pb-4"
            @submit.prevent="saveLimits"
          >
            <div class="grid">
              <span class="p-input-filled col-12 md:col-6 flex flex-column">
                <label for="ws-storage" class="mb-1">Storage (GB)</label>
                <PInputNumber
                  inputId="ws-storage"
                  v-model="form.storageGb"
                  :min="0"
                  :minFractionDigits="0"
                  :maxFractionDigits="2"
                  class="w-full"
                />
              </span>
              <span class="p-input-filled col-12 md:col-6 flex flex-column">
                <label for="ws-contributors" class="mb-1"
                  >Contributors limit</label
                >
                <PInputNumber
                  inputId="ws-contributors"
                  v-model="form.contributorsLimit"
                  :min="0"
                  :useGrouping="false"
                  placeholder="Unlimited"
                  class="w-full"
                />
                <span class="paragraph-p6 opacity-80 mt-1"
                  >Leave empty for unlimited contributors.</span
                >
              </span>
              <span class="p-input-filled col-12 flex flex-column">
                <label for="ws-description" class="mb-1">Description</label>
                <PTextarea
                  id="ws-description"
                  v-model="form.description"
                  rows="3"
                  autoResize
                  class="w-full"
                />
              </span>
            </div>
            <div class="flex justify-content-end gap-2">
              <PButton
                severity="secondary"
                label="Reset"
                :disabled="saving"
                @click="resetForm"
              />
              <PButton
                type="submit"
                label="Save changes"
                :loading="saving"
                :disabled="form.storageGb === null"
              />
            </div>
          </form>
        </app-section>
      </app-container>

      <app-container>
        <app-section>
          <template #title
            >Members
            <span class="text-color-medium-green"
              >({{ workspace.members.length }})</span
            ></template
          >
          <PDataTable
            :value="workspace.members"
            :paginator="workspace.members.length > 20"
            :rows="20"
            :rowHover="true"
            sortField="username"
            :sortOrder="1"
            data-cy="workspace-members-table"
          >
            <PColumn field="username" header="Username" sortable>
              <template #body="{ data }">
                <router-link
                  :to="{
                    name: AdminRoutes.ACCOUNT,
                    params: { username: data.username }
                  }"
                  class="title-t4"
                  >{{ data.username }}</router-link
                >
              </template>
            </PColumn>
            <PColumn field="email" header="Email" sortable />
            <PColumn field="name" header="Full name" sortable>
              <template #body="{ data }">{{ data.name || '-' }}</template>
            </PColumn>
            <PColumn field="workspace_role" header="Role" sortable>
              <template #body="{ data }">
                <PTag severity="info" :value="data.workspace_role" />
              </template>
            </PColumn>
            <PColumn field="contributor" header="Contributor" sortable>
              <template #body="{ data }">
                <i
                  :class="[
                    'ti',
                    data.contributor
                      ? 'ti-check text-color-forest'
                      : 'ti-minus opacity-60'
                  ]"
                />
              </template>
            </PColumn>
            <PColumn field="last_signed_in" header="Last signed in" sortable>
              <template #body="{ data }">{{
                data.last_signed_in
                  ? dateUtils.formatDateTime(data.last_signed_in)
                  : '-'
              }}</template>
            </PColumn>
            <template #empty>
              <p class="paragraph-p5 text-center p-4">
                Workspace has no members.
              </p>
            </template>
          </PDataTable>
        </app-section>
      </app-container>

      <app-container>
        <app-section>
          <template #title>Advanced</template>
          <app-settings :items="settingsItems">
            <template #activation>
              <div class="flex-shrink-0">
                <PButton
                  :severity="workspace.active ? 'warning' : 'secondary'"
                  :label="
                    workspace.active
                      ? 'Deactivate workspace'
                      : 'Activate workspace'
                  "
                  :disabled="!!workspace.removed_at"
                  @click="confirmToggleActive"
                />
              </div>
            </template>
            <template #removal>
              <div class="flex-shrink-0">
                <PButton
                  v-if="workspace.removed_at"
                  severity="secondary"
                  icon="ti ti-restore"
                  label="Restore workspace"
                  data-cy="workspace-restore-btn"
                  @click="restoreWorkspace"
                />
                <PButton
                  v-else
                  severity="danger"
                  label="Delete workspace"
                  data-cy="workspace-delete-btn"
                  @click="confirmDelete"
                />
              </div>
            </template>
          </app-settings>
        </app-section>
      </app-container>
    </template>
  </admin-layout>
</template>

<script setup lang="ts">
import { AdminLayout, AdminRoutes } from '@mergin/admin-lib'
import {
  AppContainer,
  AppSection,
  AppSettings,
  AppSettingsItemConfig,
  ConfirmDialog,
  ConfirmDialogProps,
  dateUtils,
  errorUtils,
  useDialogStore,
  useNotificationStore
} from '@mergin/lib'
import { computed, reactive, ref, watch, watchEffect } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { PlusAdminApi } from '../api'
import WorkspaceStatusTag from '../components/WorkspaceStatusTag.vue'
import { getPlusAdminTitle, PlusAdminRoutes } from '../routes'
import { AdminWorkspace, AdminWorkspaceDetail } from '../types'
import { bytesToGb, formatBytes, gbToBytes, usagePercent } from '../utils'

const route = useRoute()
const router = useRouter()
const dialogStore = useDialogStore()
const notificationStore = useNotificationStore()

const workspace = ref<AdminWorkspaceDetail | null>(null)
const loading = ref(false)
const saving = ref(false)
const form = reactive<{
  storageGb: number | null
  contributorsLimit: number | null
  description: string
}>({
  storageGb: null,
  contributorsLimit: null,
  description: ''
})

const workspaceId = computed(() => route.params.id as string)

const settingsItems = computed<AppSettingsItemConfig[]>(() => [
  {
    key: 'activation',
    title: 'Workspace activation',
    description: workspace.value?.active
      ? 'The workspace is active. Deactivating it blocks access to its projects for all members.'
      : 'The workspace is inactive. Activating it restores access for its members.'
  },
  {
    key: 'removal',
    title: workspace.value?.removed_at
      ? 'Restore workspace'
      : 'Delete workspace',
    description: workspace.value?.removed_at
      ? `The workspace is scheduled for removal${
          workspace.value.expiration
            ? ` on ${dateUtils.formatDateTime(workspace.value.expiration)}`
            : ''
        }. Restoring it cancels the scheduled removal.`
      : 'The workspace and all its projects will be scheduled for permanent removal. It can be restored until the removal happens.'
  }
])

const resetForm = () => {
  if (!workspace.value) return
  form.storageGb = bytesToGb(workspace.value.storage)
  form.contributorsLimit = workspace.value.contributors_limit
  form.description = workspace.value.description ?? ''
}

/** Merge updated attributes (PATCH/DELETE/restore responses do not include members) */
const applyUpdate = (data: AdminWorkspace) => {
  workspace.value = { ...workspace.value, ...data }
  resetForm()
}

const showError = (err: unknown, fallback: string) => {
  notificationStore.error({
    text: errorUtils.getErrorMessage(err, fallback)
  })
}

const fetchWorkspace = async (id: string) => {
  loading.value = true
  try {
    const response = await PlusAdminApi.fetchWorkspace(id)
    workspace.value = response.data
    resetForm()
  } catch (err) {
    workspace.value = null
    showError(err, 'Failed to load workspace')
  } finally {
    loading.value = false
  }
}

watch(
  workspaceId,
  (id) => {
    if (id) fetchWorkspace(id)
  },
  { immediate: true }
)

watchEffect(() => {
  if (workspace.value?.name) {
    const title = getPlusAdminTitle(route, {
      workspaceName: workspace.value.name
    })
    document.title = Array.isArray(title) ? title[0] : title
  }
})

const saveLimits = async () => {
  if (!workspace.value || form.storageGb === null) return
  saving.value = true
  try {
    // send storage only when changed: the GB value shown in the form is rounded
    const storageChanged = form.storageGb !== bytesToGb(workspace.value.storage)
    const response = await PlusAdminApi.updateWorkspace(workspace.value.id, {
      ...(storageChanged ? { storage: gbToBytes(form.storageGb) } : {}),
      contributors_limit: form.contributorsLimit ?? null,
      description: form.description.trim() || null
    })
    applyUpdate(response.data)
    notificationStore.show({ text: 'Workspace updated' })
  } catch (err) {
    showError(err, 'Failed to update workspace')
  } finally {
    saving.value = false
  }
}

const confirmToggleActive = () => {
  const active = workspace.value.active
  const props: ConfirmDialogProps = active
    ? {
        text: 'Do you really want to deactivate this workspace?',
        description:
          'Members will not be able to access projects of this workspace until it is activated again.',
        confirmText: 'Deactivate',
        severity: 'warning'
      }
    : {
        text: 'Do you really want to activate this workspace?',
        confirmText: 'Activate'
      }
  dialogStore.show({
    component: ConfirmDialog,
    params: {
      props,
      dialog: { header: 'Workspace activation' },
      listeners: {
        confirm: async () => {
          try {
            const response = await PlusAdminApi.updateWorkspace(
              workspace.value.id,
              { active: !active }
            )
            applyUpdate(response.data)
            notificationStore.show({
              text: active ? 'Workspace deactivated' : 'Workspace activated'
            })
          } catch (err) {
            showError(err, 'Failed to change workspace status')
          }
        }
      }
    }
  })
}

const confirmDelete = () => {
  const name = workspace.value.name
  const props: ConfirmDialogProps = {
    text: 'Are you sure you want to delete this workspace?',
    description:
      'The workspace and all its projects will be scheduled for permanent removal. Type in the workspace name to confirm:',
    hint: name,
    confirmText: 'Delete workspace',
    confirmField: { label: 'Workspace name', expected: name },
    severity: 'danger'
  }
  dialogStore.show({
    component: ConfirmDialog,
    params: {
      props,
      dialog: { header: 'Delete workspace' },
      listeners: {
        confirm: async () => {
          try {
            const response = await PlusAdminApi.deleteWorkspace(
              workspace.value.id
            )
            applyUpdate(response.data)
            notificationStore.show({
              text: `Workspace ${name} scheduled for removal`
            })
          } catch (err) {
            showError(err, 'Failed to delete workspace')
          }
        }
      }
    }
  })
}

const openActivityLog = () => {
  router.push({
    name: PlusAdminRoutes.AUDIT,
    query: { workspace_id: String(workspace.value.id) }
  })
}

const restoreWorkspace = async () => {
  try {
    const response = await PlusAdminApi.restoreWorkspace(workspace.value.id)
    applyUpdate(response.data)
    notificationStore.show({ text: 'Workspace restored' })
  } catch (err) {
    showError(err, 'Failed to restore workspace')
  }
}
</script>
