<!--
Copyright (C) Lutra Consulting Limited

SPDX-License-Identifier: LicenseRef-MerginMaps-Commercial
-->

<script setup lang="ts">
import { AdminRoutes, SidebarFooter } from '@mergin/admin-lib'
import {
  SideBarItemModel,
  SideBarTemplate,
  useInstanceStore
} from '@mergin/lib'
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { PlusAdminRoutes } from '@/modules/plus/routes'

const route = useRoute()
const instanceStore = useInstanceStore()

/** Ory Polis admin UI, shown only when SSO is enabled and its URL is exposed in /config */
const ssoServerUrl = computed<string | null>(() => {
  const config = instanceStore.configData
  const url = config?.sso_server_url
  return config?.sso_enabled && typeof url === 'string' && url ? url : null
})

const sidebarItems = computed<SideBarItemModel[]>(() => [
  {
    title: 'Overview',
    to: '/overview',
    icon: 'ti ti-layout-dashboard',
    active: route.matched.some((item) => item.name === AdminRoutes.OVERVIEW)
  },
  {
    title: 'Accounts',
    to: '/accounts',
    icon: 'ti ti-user-circle',
    active: route.matched.some((item) => item.name === AdminRoutes.ACCOUNTS)
  },
  {
    title: 'Projects',
    to: '/projects',
    icon: 'ti ti-article',
    active: route.matched.some((item) => item.name === AdminRoutes.PROJECTS)
  },
  {
    title: 'Workspaces',
    to: '/workspaces',
    icon: 'ti ti-building',
    active: route.matched.some(
      (item) =>
        item.name === PlusAdminRoutes.WORKSPACES ||
        item.name === PlusAdminRoutes.WORKSPACE
    )
  },
  {
    title: 'Activity log',
    to: '/audit',
    icon: 'ti ti-history',
    active: route.matched.some((item) => item.name === PlusAdminRoutes.AUDIT)
  },
  {
    title: 'Settings',
    to: '/settings',
    icon: 'ti ti-settings',
    active: route.matched.some((item) => item.name === AdminRoutes.SETTINGS)
  },
  ...(ssoServerUrl.value
    ? [
        {
          title: 'SSO administration',
          href: ssoServerUrl.value,
          icon: 'ti ti-key'
        }
      ]
    : [])
])
</script>

<template>
  <side-bar-template :sidebarItems="sidebarItems">
    <template #subtitle>Admin panel</template>
    <template #footer>
      <sidebar-footer />
    </template>
  </side-bar-template>
</template>

<style lang="scss" scoped></style>
