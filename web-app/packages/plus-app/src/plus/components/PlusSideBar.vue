<!--
Copyright (C) 2026 merginmaps-server contributors

SPDX-License-Identifier: AGPL-3.0-only
-->

<template>
  <side-bar-template>
    <template v-if="instanceName" #subtitle>{{ instanceName }}</template>
  </side-bar-template>
</template>

<script setup lang="ts">
import { SideBarTemplate, useInstanceStore } from '@mergin/lib'
import { computed, watchEffect } from 'vue'

// branding: INSTANCE_NAME (logo comes from DASHBOARD_LOGO_URL, handled by CE sidebar)
const instanceStore = useInstanceStore()
const instanceName = computed(
  () => instanceStore.configData?.['instance_name'] as string | undefined
)

watchEffect(() => {
  if (instanceName.value && !document.title.includes(instanceName.value)) {
    document.title = `${document.title} · ${instanceName.value}`
  }
})
</script>
