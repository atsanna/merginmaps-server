<!--
Copyright (C) 2026 merginmaps-server contributors

SPDX-License-Identifier: AGPL-3.0-only
-->

<template>
  <app-container>
    <app-section v-if="invitations.length" class="mb-3">
      <template #title>Pending invitations</template>
      <PDataTable :value="invitations" data-key="uuid">
        <PColumn field="workspace" header="Workspace" />
        <PColumn header="Role">
          <template #body="{ data }">
            <PTag :value="data.role" severity="info" />
          </template>
        </PColumn>
        <PColumn field="inviter" header="Invited by" />
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
              @click="accept(data)"
            />
            <PButton
              label="Decline"
              size="small"
              severity="secondary"
              @click="decline(data)"
            />
          </template>
        </PColumn>
      </PDataTable>
    </app-section>

    <app-section>
      <template #title>Your workspaces</template>
      <template #headerActions>
        <PButton
          v-if="canCreate"
          icon="ti ti-plus"
          label="Create workspace"
          @click="createVisible = true"
        />
      </template>
      <PDataTable :value="userStore.workspaces" data-key="id">
        <PColumn field="name" header="Name">
          <template #body="{ data }">
            <span class="font-semibold">{{ data.name }}</span>
            <PTag
              v-if="data.id === userStore.currentWorkspace?.id"
              class="ml-2"
              value="current"
              severity="success"
            />
          </template>
        </PColumn>
        <PColumn header="Role">
          <template #body="{ data }">{{ data.role }}</template>
        </PColumn>
        <PColumn header="Projects" field="project_count" />
        <PColumn header="Storage">
          <template #body="{ data }"
            >{{ $filters.filesize(data.disk_usage) }} /
            {{ $filters.filesize(data.storage) }}</template
          >
        </PColumn>
        <PColumn header="" body-class="text-right">
          <template #body="{ data }">
            <PButton
              v-if="data.id !== userStore.currentWorkspace?.id"
              label="Switch"
              size="small"
              class="mr-2"
              @click="switchTo(data.id)"
            />
            <PButton
              v-if="data.role !== 'guest'"
              label="Leave"
              size="small"
              severity="secondary"
              @click="leave(data)"
            />
          </template>
        </PColumn>
      </PDataTable>
    </app-section>

    <PDialog
      :visible="createVisible"
      @update:visible="createVisible = $event"
      header="Create workspace"
      modal
      :style="{ width: '32rem' }"
    >
      <div class="flex flex-column gap-3">
        <span class="paragraph-p6 opacity-80"
          >The workspace name is part of project addresses and can not be
          changed later.</span
        >
        <label for="ws-name" class="font-semibold">Name</label>
        <PInputText id="ws-name" v-model="newName" autofocus />
        <label for="ws-description" class="font-semibold">Description</label>
        <PTextarea id="ws-description" v-model="newDescription" rows="3" />
      </div>
      <template #footer>
        <PButton
          label="Cancel"
          severity="secondary"
          @click="createVisible = false"
        />
        <PButton label="Create" :disabled="!newName" @click="create" />
      </template>
    </PDialog>
  </app-container>
</template>

<script setup lang="ts">
import {
  AppContainer,
  AppSection,
  useInstanceStore,
  useNotificationStore,
  useUserStore
} from '@mergin/lib'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { Invitation, PlusApi, apiError } from '@/plus/api'
import { usePlusStore } from '@/plus/store'

const userStore = useUserStore()
const instanceStore = useInstanceStore()
const notificationStore = useNotificationStore()
const plusStore = usePlusStore()
const router = useRouter()

const invitations = computed(() => plusStore.invitations)
const createVisible = ref(false)
const newName = ref('')
const newDescription = ref('')
const canCreate = computed(
  () =>
    instanceStore.configData?.user_workspaces_allowed !== false ||
    userStore.loggedUser?.is_admin
)

async function refresh() {
  await Promise.all([userStore.getWorkspaces(), plusStore.fetchInvitations()])
}

onMounted(refresh)

async function switchTo(id: number) {
  await userStore.setWorkspace({ workspaceId: id })
  await router.push({ path: '/dashboard' })
}

async function create() {
  try {
    const resp = await PlusApi.createWorkspace({
      name: newName.value.trim(),
      description: newDescription.value || undefined
    })
    createVisible.value = false
    newName.value = ''
    newDescription.value = ''
    await userStore.getWorkspaces()
    await switchTo(resp.data.id)
    notificationStore.show({ text: `Workspace ${resp.data.name} created` })
  } catch (err) {
    notificationStore.error({
      text: apiError(err, 'Failed to create workspace')
    })
  }
}

async function leave(ws: { id: number; name: string }) {
  if (!confirm(`Leave workspace ${ws.name}?`)) return
  try {
    await PlusApi.removeMember(ws.id, userStore.loggedUser.id)
    await userStore.getWorkspaces()
    await userStore.checkCurrentWorkspace()
    notificationStore.show({ text: `You left workspace ${ws.name}` })
  } catch (err) {
    notificationStore.error({
      text: apiError(err, 'Failed to leave workspace')
    })
  }
}

async function accept(inv: Invitation) {
  try {
    await PlusApi.acceptInvitation(inv.uuid)
    await refresh()
    notificationStore.show({ text: `You joined workspace ${inv.workspace}` })
  } catch (err) {
    notificationStore.error({
      text: apiError(err, 'Failed to accept invitation')
    })
  }
}

async function decline(inv: Invitation) {
  try {
    await PlusApi.declineInvitation(inv.uuid)
    await plusStore.fetchInvitations()
  } catch (err) {
    notificationStore.error({
      text: apiError(err, 'Failed to decline invitation')
    })
  }
}
</script>
