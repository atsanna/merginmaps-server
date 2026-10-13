<!--
Copyright (C) Lutra Consulting Limited

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-MerginMaps-Commercial
-->

<template>
  <app-header-template :renderNamespace="true" :menu-items="menuItems">
    <template #invitationsIcon>
      <i
        v-if="plusStore.invitations.length"
        v-tooltip.bottom="'Pending invitations'"
        class="ti ti-mail mr-2 text-orange-500"
        v-badge.danger="plusStore.invitations.length"
      ></i>
    </template>
  </app-header-template>
</template>

<script lang="ts" setup>
import { AppHeaderTemplate, useUserStore } from '@mergin/lib'
import { MenuItem } from 'primevue/menuitem'
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

import { usePlusStore } from '@/plus/store'

const userStore = useUserStore()
const plusStore = usePlusStore()
const router = useRouter()

onMounted(() => plusStore.fetchInvitations())

// workspace switcher (recently used first) and workspace management
const menuItems = computed<MenuItem[]>(() => {
  const recent = [...userStore.lastWorkspaces.value]
    .filter((item) => item.userId === userStore.loggedUser?.id)
    .sort((a, b) => b.lastSeen - a.lastSeen)
    .map((item) => item.id)
  const workspaces = [...userStore.workspaces].sort((a, b) => {
    const ia = recent.indexOf(a.id)
    const ib = recent.indexOf(b.id)
    return (ia === -1 ? 1e6 : ia) - (ib === -1 ? 1e6 : ib)
  })
  const items: MenuItem[] = workspaces.slice(0, 5).map((ws) => ({
    label: ws.name,
    icon:
      ws.id === userStore.currentWorkspace?.id
        ? 'ti ti-circle-check'
        : 'ti ti-building',
    command: async () => {
      await userStore.setWorkspace({ workspaceId: ws.id })
      await router.push({ path: '/dashboard' })
    }
  }))
  items.push({
    label: plusStore.invitations.length
      ? `Manage workspaces (${plusStore.invitations.length} invitations)`
      : 'Manage workspaces',
    icon: 'ti ti-settings',
    command: () => router.push({ path: '/workspaces' })
  })
  if (userStore.isWorkspaceAdmin()) {
    items.push(
      {
        label: 'Workspace members',
        icon: 'ti ti-users',
        command: () => router.push({ path: '/workspace/members' })
      },
      {
        label: 'Workspace settings',
        icon: 'ti ti-adjustments',
        command: () => router.push({ path: '/workspace/settings' })
      }
    )
  }
  items.push({ separator: true })
  return items
})
</script>

<style lang="scss" scoped></style>
