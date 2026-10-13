<!--
Copyright (C) 2026 merginmaps-server contributors

SPDX-License-Identifier: AGPL-3.0-only
-->

<template>
  <app-settings-item v-if="projectId">
    <template #title>Transfer project</template>
    <template #description>
      <template v-if="transfer"
        >Transfer to workspace <b>{{ transfer.to_workspace }}</b> is waiting for
        approval until {{ $filters.datetime(transfer.expires_at) }}. Ask
        collaborators to synchronise their changes before it is
        accepted.</template
      >
      <template v-else
        >Move the project to another workspace. Its administrators have to
        accept the transfer.</template
      >
    </template>
    <template #action>
      <div class="flex gap-2 flex-shrink-0">
        <template v-if="transfer">
          <PButton
            severity="secondary"
            label="Cancel transfer"
            @click="cancel"
          />
        </template>
        <template v-else>
          <PInputText v-model="target" placeholder="Workspace name" />
          <PButton
            severity="secondary"
            label="Request transfer"
            :disabled="!target"
            @click="request"
          />
        </template>
      </div>
    </template>
  </app-settings-item>
</template>

<script setup lang="ts">
import {
  AppSettingsItem,
  useNotificationStore,
  useProjectStore
} from '@mergin/lib'
import { computed, ref, watch } from 'vue'

import { PlusApi, Transfer, apiError } from '@/plus/api'

const projectStore = useProjectStore()
const notificationStore = useNotificationStore()
const projectId = computed<string | undefined>(() => projectStore.project?.id)
const transfer = ref<Transfer>()
const target = ref('')

async function load() {
  transfer.value = undefined
  if (!projectId.value) return
  try {
    transfer.value = (await PlusApi.projectTransfer(projectId.value)).data
  } catch {
    // no pending transfer
  }
}

watch(projectId, load, { immediate: true })

async function request() {
  try {
    const resp = await PlusApi.requestTransfer(
      projectId.value,
      target.value.trim()
    )
    transfer.value = resp.data
    target.value = ''
    notificationStore.show({ text: 'Transfer requested' })
  } catch (err) {
    notificationStore.error({
      text: apiError(err, 'Failed to request transfer')
    })
  }
}

async function cancel() {
  try {
    await PlusApi.removeTransfer(transfer.value.id)
    transfer.value = undefined
  } catch (err) {
    notificationStore.error({
      text: apiError(err, 'Failed to cancel transfer')
    })
  }
}
</script>
