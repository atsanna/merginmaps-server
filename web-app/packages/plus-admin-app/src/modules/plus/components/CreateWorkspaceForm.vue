<!--
Copyright (C) 2026 merginmaps-server contributors

SPDX-License-Identifier: AGPL-3.0-only
-->

<template>
  <form @submit.prevent="submit" class="flex flex-column row-gap-3 pb-4">
    <span class="p-input-filled flex flex-column row-gap-1">
      <label for="workspace-name">Name</label>
      <PInputText
        id="workspace-name"
        v-model="name"
        :class="['w-full', nameError ? 'p-invalid' : '']"
        aria-describedby="workspace-name-error"
        autofocus
      />
      <span class="p-error paragraph-p6" id="workspace-name-error">{{
        nameError || '&nbsp;'
      }}</span>
    </span>

    <span class="p-input-filled flex flex-column row-gap-1">
      <label for="workspace-description">Description</label>
      <PTextarea
        id="workspace-description"
        v-model="description"
        rows="3"
        autoResize
        class="w-full"
      />
    </span>

    <span class="p-input-filled flex flex-column row-gap-1">
      <label for="workspace-storage">Storage (GB)</label>
      <PInputNumber
        inputId="workspace-storage"
        v-model="storageGb"
        :min="0"
        :minFractionDigits="0"
        :maxFractionDigits="2"
        placeholder="Server default"
        class="w-full"
      />
    </span>

    <span class="p-input-filled flex flex-column row-gap-1">
      <label for="workspace-contributors">Contributors limit</label>
      <PInputNumber
        inputId="workspace-contributors"
        v-model="contributorsLimit"
        :min="0"
        :useGrouping="false"
        placeholder="Unlimited"
        class="w-full"
      />
      <span class="paragraph-p6 opacity-80"
        >Leave empty for unlimited contributors.</span
      >
    </span>

    <div
      class="w-full flex flex-column lg:flex-row justify-content-between align-items-center mt-4"
    >
      <PButton
        severity="secondary"
        @click="close"
        class="flex w-12 mb-2 lg:mb-0 lg:mr-2 lg:w-6 justify-content-center"
        label="Cancel"
      />
      <PButton
        type="submit"
        class="flex w-12 lg:w-6 justify-content-center"
        :loading="loading"
        :disabled="!name.trim()"
        label="Create"
      />
    </div>
  </form>
</template>

<script setup lang="ts">
import { errorUtils, useDialogStore, useNotificationStore } from '@mergin/lib'
import { ref } from 'vue'

import { PlusAdminApi } from '../api'
import { CreateWorkspaceData } from '../types'
import { gbToBytes } from '../utils'

const emit = defineEmits<{ (e: 'success'): void }>()

const dialogStore = useDialogStore()
const notificationStore = useNotificationStore()

const name = ref('')
const description = ref('')
const storageGb = ref<number | null>(null)
const contributorsLimit = ref<number | null>(null)
const loading = ref(false)
const nameError = ref<string | null>(null)

const close = () => dialogStore.close()

const submit = async () => {
  nameError.value = null
  if (!name.value.trim()) {
    nameError.value = 'Name is required'
    return
  }
  const data: CreateWorkspaceData = {
    name: name.value.trim(),
    description: description.value.trim() || null,
    contributors_limit: contributorsLimit.value ?? null
  }
  if (storageGb.value !== null && storageGb.value !== undefined) {
    data.storage = gbToBytes(storageGb.value)
  }
  loading.value = true
  try {
    await PlusAdminApi.createWorkspace(data)
    close()
    emit('success')
    notificationStore.show({ text: `Workspace ${data.name} created` })
  } catch (err) {
    const message = errorUtils.getErrorMessage(
      err,
      'Failed to create workspace'
    )
    nameError.value = message
    notificationStore.error({ text: message })
  } finally {
    loading.value = false
  }
}
</script>
