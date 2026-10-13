<!--
Copyright (C) 2026 merginmaps-server contributors

SPDX-License-Identifier: AGPL-3.0-only
-->

<template>
  <PTag
    v-if="workspace.removed_at"
    severity="danger"
    :value="
      workspace.expiration
        ? `Scheduled for removal (${dateUtils.formatDate(
            workspace.expiration
          )})`
        : 'Scheduled for removal'
    "
  />
  <PTag v-else-if="workspace.active" severity="success" value="Active" />
  <PTag v-else severity="warning" value="Inactive" />
</template>

<script setup lang="ts">
import { dateUtils } from '@mergin/lib'

import { AdminWorkspace } from '../types'

defineProps<{
  workspace: Pick<AdminWorkspace, 'active' | 'removed_at' | 'expiration'>
}>()
</script>
