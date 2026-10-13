// Copyright (C) 2026 merginmaps-server contributors
//
// SPDX-License-Identifier: AGPL-3.0-only

/* eslint-disable camelcase */

export interface PaginatedResponse<T> {
  items: T[]
  count: number
}

export interface AdminWorkspace {
  id: number
  name: string
  description: string | null
  active: boolean
  /** Storage limit in bytes */
  storage: number
  /** Used storage in bytes */
  disk_usage: number
  project_count: number
  members_count: number
  contributors_count: number
  /** null means unlimited */
  contributors_limit: number | null
  created: string
  removed_at: string | null
  expiration: string | null
}

export interface AdminWorkspaceMember {
  id: number
  username: string
  email: string
  name: string | null
  workspace_role: string
  contributor: boolean
  last_signed_in: string | null
}

export interface AdminWorkspaceDetail extends AdminWorkspace {
  members: AdminWorkspaceMember[]
}

export interface AdminWorkspacesParams {
  page: number
  per_page: number
  order_params?: string
  like?: string
}

export interface CreateWorkspaceData {
  name: string
  description?: string | null
  storage?: number
  contributors_limit?: number | null
}

export interface UpdateWorkspaceData {
  storage?: number
  contributors_limit?: number | null
  description?: string | null
  active?: boolean
}

export interface AuditEvent {
  id: number
  event_type: string
  happened_at: string
  actor_email: string | null
  actor_ip: string | null
  target_workspace_id: number | null
  target_project_id: string | null
  target_user_id: number | null
  metadata: Record<string, unknown> | null
}

export interface AuditParams {
  page: number
  per_page: number
  event_type?: string
  workspace_id?: number
  since?: string
  until?: string
}

/* eslint-enable camelcase */
