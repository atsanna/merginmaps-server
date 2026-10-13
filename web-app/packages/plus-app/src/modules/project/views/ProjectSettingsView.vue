<!--
Copyright (C) Lutra Consulting Limited

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-MerginMaps-Commercial
-->

<template>
  <project-settings-view-template
    :namespace="namespace"
    :projectName="projectName"
    :show-settings="projectStore.isProjectOwner"
  >
    <template #operations>
      <project-transfer-item />
    </template>
  </project-settings-view-template>
</template>

<script setup lang="ts">
import { ProjectSettingsViewTemplate, useProjectStore } from '@mergin/lib'

import ProjectTransferItem from '@/plus/components/ProjectTransferItem.vue'

defineProps<{ namespace: string; projectName: string }>()

const projectStore = useProjectStore()
</script>
