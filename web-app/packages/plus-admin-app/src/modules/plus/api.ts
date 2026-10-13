// Copyright (C) 2026 merginmaps-server contributors
//
// SPDX-License-Identifier: AGPL-3.0-only

import { getHttpService } from '@mergin/lib'

import {
  AdminWorkspace,
  AdminWorkspaceDetail,
  AdminWorkspacesParams,
  AuditEvent,
  AuditParams,
  CreateWorkspaceData,
  PaginatedResponse,
  UpdateWorkspaceData
} from './types'

const WORKSPACES_URL = '/app/admin/workspaces'
const AUDIT_URL = '/app/admin/audit'

export const PlusAdminApi = {
  fetchWorkspaces(params: AdminWorkspacesParams, signal?: AbortSignal) {
    return getHttpService().get<PaginatedResponse<AdminWorkspace>>(
      WORKSPACES_URL,
      { params, signal }
    )
  },

  createWorkspace(data: CreateWorkspaceData) {
    return getHttpService().post<AdminWorkspace>(WORKSPACES_URL, data)
  },

  fetchWorkspace(id: number | string) {
    return getHttpService().get<AdminWorkspaceDetail>(`${WORKSPACES_URL}/${id}`)
  },

  updateWorkspace(id: number | string, data: UpdateWorkspaceData) {
    return getHttpService().patch<AdminWorkspace>(
      `${WORKSPACES_URL}/${id}`,
      data
    )
  },

  deleteWorkspace(id: number | string) {
    return getHttpService().delete<AdminWorkspace>(`${WORKSPACES_URL}/${id}`)
  },

  restoreWorkspace(id: number | string) {
    return getHttpService().post<AdminWorkspace>(
      `${WORKSPACES_URL}/${id}/restore`
    )
  },

  fetchAuditEvents(params: AuditParams, signal?: AbortSignal) {
    return getHttpService().get<PaginatedResponse<AuditEvent>>(AUDIT_URL, {
      params,
      signal
    })
  }
}
