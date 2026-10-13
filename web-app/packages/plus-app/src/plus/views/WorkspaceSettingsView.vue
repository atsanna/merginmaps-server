<!--
Copyright (C) 2026 merginmaps-server contributors

SPDX-License-Identifier: AGPL-3.0-only
-->

<template>
  <app-container v-if="workspace">
    <PTabView
      :active-index="activeTab"
      @update:active-index="activeTab = $event"
    >
      <PTabPanel header="General">
        <app-section class="mb-3">
          <template #title>{{ workspace.name }}</template>
          <div class="p-4 flex flex-column gap-3">
            <div v-if="usage" class="flex flex-wrap gap-4">
              <span
                ><b>Storage</b> {{ $filters.filesize(usage.disk_usage) }} /
                {{ $filters.filesize(usage.storage) }}</span
              >
              <span><b>Projects</b> {{ usage.project_count }}</span>
              <span><b>Members</b> {{ usage.members_count }}</span>
              <span
                ><b>Contributors</b> {{ usage.contributors_count }} /
                {{ usage.contributors_limit ?? 'unlimited' }}</span
              >
            </div>
            <label for="ws-description" class="font-semibold"
              >Description</label
            >
            <PTextarea
              id="ws-description"
              v-model="description"
              rows="3"
              :disabled="!isOwner"
            />
            <div>
              <PButton
                v-if="isOwner"
                label="Save description"
                @click="saveDescription"
              />
            </div>
          </div>
        </app-section>
        <app-section v-if="isOwner">
          <app-settings>
            <app-settings-item>
              <template #title>Close workspace</template>
              <template #description
                >The workspace and all its projects are removed permanently
                after a few days. Type the workspace name to confirm.</template
              >
              <template #action>
                <div class="flex gap-2 flex-shrink-0">
                  <PInputText
                    v-model="closeConfirm"
                    :placeholder="workspace.name"
                  />
                  <PButton
                    severity="danger"
                    label="Close workspace"
                    :disabled="closeConfirm !== workspace.name"
                    @click="closeWorkspace"
                  />
                </div>
              </template>
            </app-settings-item>
          </app-settings>
        </app-section>
      </PTabPanel>

      <PTabPanel header="Transfers">
        <app-section class="mb-3">
          <template #title>Incoming project transfers</template>
          <PDataTable :value="transfers.incoming" data-key="id">
            <template #empty>No incoming transfers</template>
            <PColumn header="Project">
              <template #body="{ data }"
                >{{ data.from_workspace }}/{{ data.project_name }}</template
              >
            </PColumn>
            <PColumn field="requested_by" header="Requested by" />
            <PColumn header="Expires">
              <template #body="{ data }">{{
                $filters.datetime(data.expires_at)
              }}</template>
            </PColumn>
            <PColumn header="" body-class="text-right">
              <template #body="{ data }">
                <PButton
                  label="Accept"
                  size="small"
                  class="mr-2"
                  @click="acceptTransfer(data)"
                />
                <PButton
                  label="Decline"
                  size="small"
                  severity="secondary"
                  @click="removeTransfer(data)"
                />
              </template>
            </PColumn>
          </PDataTable>
        </app-section>
        <app-section>
          <template #title>Outgoing project transfers</template>
          <PDataTable :value="transfers.outgoing" data-key="id">
            <template #empty>No outgoing transfers</template>
            <PColumn field="project_name" header="Project" />
            <PColumn field="to_workspace" header="To workspace" />
            <PColumn header="Expires">
              <template #body="{ data }">{{
                $filters.datetime(data.expires_at)
              }}</template>
            </PColumn>
            <PColumn header="" body-class="text-right">
              <template #body="{ data }">
                <PButton
                  label="Cancel"
                  size="small"
                  severity="secondary"
                  @click="removeTransfer(data)"
                />
              </template>
            </PColumn>
          </PDataTable>
        </app-section>
      </PTabPanel>

      <PTabPanel header="Webhooks">
        <app-section>
          <template #title>Webhooks</template>
          <div class="p-4 flex flex-column gap-2">
            <span class="paragraph-p6 opacity-80"
              >Workspace events are sent as JSON with a
              <code>X-Webhook-Signature</code> header (HMAC-SHA256 of the body
              with the webhook secret). Leave event types empty to receive all
              events, or list prefixes like <code>project.version</code>.</span
            >
            <div class="flex flex-wrap gap-2">
              <PInputText
                v-model="hookUrl"
                placeholder="https://example.com/webhook"
                class="flex-grow-1"
              />
              <PInputText
                v-model="hookEvents"
                placeholder="event types, comma separated"
              />
              <PButton label="Add" :disabled="!hookUrl" @click="addWebhook" />
            </div>
            <PMessage v-if="newSecret" severity="warn" :closable="false"
              >Copy the secret now, it will not be shown again:
              <code>{{ newSecret }}</code></PMessage
            >
          </div>
          <PDataTable :value="webhooks" data-key="id">
            <template #empty>No webhooks</template>
            <PColumn field="url" header="URL" />
            <PColumn header="Events">
              <template #body="{ data }">{{
                data.events.length ? data.events.join(', ') : 'all'
              }}</template>
            </PColumn>
            <PColumn header="Last delivery">
              <template #body="{ data }">
                <span v-if="data.last_delivery_at"
                  >{{ $filters.datetime(data.last_delivery_at) }} ({{
                    data.last_status ?? data.last_error
                  }})</span
                >
                <span v-else>-</span>
              </template>
            </PColumn>
            <PColumn header="Active">
              <template #body="{ data }">
                <PInputSwitch
                  :model-value="data.active"
                  @update:model-value="(v) => toggleWebhook(data, v)"
                />
              </template>
            </PColumn>
            <PColumn header="" body-class="text-right">
              <template #body="{ data }">
                <PButton
                  label="Test"
                  size="small"
                  severity="secondary"
                  class="mr-2"
                  @click="pingWebhook(data)"
                />
                <PButton
                  icon="ti ti-trash"
                  text
                  severity="danger"
                  aria-label="Delete webhook"
                  @click="deleteWebhook(data)"
                />
              </template>
            </PColumn>
          </PDataTable>
        </app-section>
      </PTabPanel>

      <PTabPanel header="Activity">
        <app-section>
          <template #title>Activity log</template>
          <template #headerActions>
            <PInputText
              v-model="eventFilter"
              placeholder="Event type, e.g. project.member"
              @keyup.enter="loadAudit(1)"
            />
          </template>
          <PDataTable
            :value="audit.items"
            data-key="id"
            lazy
            paginator
            :first="(auditPage - 1) * perPage"
            :rows="perPage"
            :total-records="audit.count"
            @page="(e) => loadAudit(e.page + 1)"
          >
            <PColumn header="When">
              <template #body="{ data }">{{
                $filters.datetime(data.happened_at)
              }}</template>
            </PColumn>
            <PColumn field="event_type" header="Event" />
            <PColumn field="actor_email" header="By" />
            <PColumn header="Details">
              <template #body="{ data }">
                <code class="paragraph-p6">{{ details(data.metadata) }}</code>
              </template>
            </PColumn>
          </PDataTable>
        </app-section>
      </PTabPanel>
    </PTabView>
  </app-container>
</template>

<script setup lang="ts">
import {
  AppContainer,
  AppSection,
  AppSettings,
  AppSettingsItem,
  useNotificationStore,
  useUserStore
} from '@mergin/lib'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  AuditEvent,
  Page,
  PlusApi,
  Transfer,
  Webhook,
  WorkspaceUsage,
  apiError
} from '@/plus/api'

const userStore = useUserStore()
const notificationStore = useNotificationStore()
const router = useRouter()

const workspace = computed(() => userStore.currentWorkspace)
const isOwner = computed(() => userStore.isWorkspaceOwner())
const usage = ref<WorkspaceUsage>()
const description = ref('')
const closeConfirm = ref('')
const transfers = ref<{ incoming: Transfer[]; outgoing: Transfer[] }>({
  incoming: [],
  outgoing: []
})
const webhooks = ref<Webhook[]>([])
const hookUrl = ref('')
const hookEvents = ref('')
const newSecret = ref('')
const audit = ref<Page<AuditEvent>>({ items: [], count: 0 })
const perPage = 25
const auditPage = ref(1)
const route = useRoute()
const TABS = ['general', 'transfers', 'webhooks', 'activity']
const activeTab = ref(Math.max(0, TABS.indexOf(String(route.query.tab ?? ''))))
const eventFilter = ref('')

async function load() {
  if (!workspace.value) return
  const id = workspace.value.id
  description.value = workspace.value.description ?? ''
  try {
    const [u, t, w] = await Promise.all([
      PlusApi.workspaceUsage(id),
      PlusApi.workspaceTransfers(id),
      PlusApi.webhooks(id)
    ])
    usage.value = u.data
    transfers.value = t.data
    webhooks.value = w.data
    await loadAudit(1)
  } catch (err) {
    notificationStore.error({
      text: apiError(err, 'Failed to load workspace settings')
    })
  }
}

watch(workspace, load, { immediate: true })

async function loadAudit(page: number) {
  try {
    const resp = await PlusApi.workspaceAudit(workspace.value.id, {
      page,
      per_page: perPage,
      event_type: eventFilter.value.trim() || undefined
    })
    audit.value = resp.data
    auditPage.value = page
  } catch (err) {
    notificationStore.error({ text: apiError(err, 'Failed to load activity') })
  }
}

function details(metadata: Record<string, unknown>) {
  const text = JSON.stringify(metadata)
  return text.length > 120 ? text.slice(0, 117) + '...' : text
}

async function saveDescription() {
  try {
    await PlusApi.updateWorkspace(workspace.value.id, {
      description: description.value
    })
    await userStore.getWorkspaces()
    notificationStore.show({ text: 'Description saved' })
  } catch (err) {
    notificationStore.error({ text: apiError(err, 'Failed to save') })
  }
}

async function closeWorkspace() {
  try {
    await PlusApi.closeWorkspace(workspace.value.id)
    await userStore.getWorkspaces()
    await userStore.checkCurrentWorkspace()
    notificationStore.show({ text: 'Workspace closed' })
    await router.push({ path: '/workspaces' })
  } catch (err) {
    notificationStore.error({
      text: apiError(err, 'Failed to close workspace')
    })
  }
}

async function acceptTransfer(transfer: Transfer) {
  try {
    await PlusApi.acceptTransfer(transfer.id)
  } catch (err) {
    // project with the same name already exists in this workspace
    const status = (err as { response?: { status?: number } })?.response?.status
    if (status !== 409) {
      notificationStore.error({
        text: apiError(err, 'Failed to accept transfer')
      })
      return
    }
    const name = prompt(
      `Project ${transfer.project_name} already exists, new project name:`
    )
    if (!name) return
    try {
      await PlusApi.acceptTransfer(transfer.id, name)
    } catch (err2) {
      notificationStore.error({
        text: apiError(err2, 'Failed to accept transfer')
      })
      return
    }
  }
  notificationStore.show({ text: 'Project transferred' })
  await load()
}

async function removeTransfer(transfer: Transfer) {
  try {
    await PlusApi.removeTransfer(transfer.id)
    await load()
  } catch (err) {
    notificationStore.error({
      text: apiError(err, 'Failed to remove transfer')
    })
  }
}

async function addWebhook() {
  try {
    const resp = await PlusApi.createWebhook(workspace.value.id, {
      url: hookUrl.value.trim(),
      events: hookEvents.value
        .split(',')
        .map((e) => e.trim())
        .filter(Boolean)
    })
    newSecret.value = resp.data.secret ?? ''
    hookUrl.value = ''
    hookEvents.value = ''
    await load()
  } catch (err) {
    notificationStore.error({ text: apiError(err, 'Failed to add webhook') })
  }
}

async function toggleWebhook(hook: Webhook, active: boolean) {
  try {
    await PlusApi.updateWebhook(workspace.value.id, hook.id, { active })
    await load()
  } catch (err) {
    notificationStore.error({ text: apiError(err, 'Failed to update webhook') })
  }
}

async function pingWebhook(hook: Webhook) {
  let resp
  try {
    resp = await PlusApi.pingWebhook(workspace.value.id, hook.id)
  } catch (err) {
    notificationStore.error({ text: apiError(err, 'Failed to test webhook') })
    return
  }
  if (resp.data.ok) {
    notificationStore.show({ text: `Test delivered (${resp.data.status})` })
  } else {
    notificationStore.error({
      text: `Test failed: ${resp.data.error ?? resp.data.status}`
    })
  }
}

async function deleteWebhook(hook: Webhook) {
  if (!confirm(`Delete webhook ${hook.url}?`)) return
  try {
    await PlusApi.deleteWebhook(workspace.value.id, hook.id)
    await load()
  } catch (err) {
    notificationStore.error({ text: apiError(err, 'Failed to delete webhook') })
  }
}
</script>
