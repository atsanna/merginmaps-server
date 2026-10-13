// Copyright (C) 2026 merginmaps-server contributors
//
// SPDX-License-Identifier: AGPL-3.0-only

import { getAdminTitle } from '@mergin/admin-lib'
import { RouteLocationNormalizedLoaded } from 'vue-router'

export const PlusAdminRoutes = {
  WORKSPACES: 'plus-workspaces',
  WORKSPACE: 'plus-workspace',
  AUDIT: 'plus-audit'
} as const

export type PlusAdminRouteName =
  typeof PlusAdminRoutes[keyof typeof PlusAdminRoutes]

/** Page titles of add-on routes, falls back to CE admin titles. */
export const getPlusAdminTitle = (
  route: RouteLocationNormalizedLoaded,
  config?: { accountEmail?: string; workspaceName?: string }
): string | string[] => {
  const titles: Record<PlusAdminRouteName, string | string[]> = {
    [PlusAdminRoutes.WORKSPACES]: 'Workspaces',
    [PlusAdminRoutes.WORKSPACE]: [config?.workspaceName || 'Workspace details'],
    [PlusAdminRoutes.AUDIT]: 'Activity log'
  }
  return (
    titles[route.name as PlusAdminRouteName] ?? getAdminTitle(route, config)
  )
}
