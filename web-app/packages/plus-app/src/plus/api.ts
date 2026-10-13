// Copyright (C) 2026 merginmaps-server contributors
//
// SPDX-License-Identifier: AGPL-3.0-only

import { getHttpService } from '@mergin/lib'

export type MemberRole = 'reader' | 'editor' | 'writer' | 'admin' | 'owner'
export type InvitationRole = MemberRole | 'guest'
export type ProjectRoleName = 'reader' | 'editor' | 'writer' | 'owner'

export interface Member {
  id: number
  username: string
  email: string
  name: string | null
  workspace_role: InvitationRole
  contributor: boolean
  last_signed_in: string | null
}

export interface InvitationProject {
  id: string
  role: ProjectRoleName
}

export interface Invitation {
  uuid: string
  email: string
  role: InvitationRole
  workspace_id: number
  workspace: string
  inviter: string | null
  created: string
  expires_at: string
  expired: boolean
  projects: InvitationProject[]
}

export interface WorkspaceUsage {
  storage: number
  disk_usage: number
  project_count: number
  members_count: number
  contributors_count: number
  contributors_limit: number | null
}

export interface Transfer {
  id: string
  project_id: string
  project_name: string
  from_workspace_id: number
  from_workspace: string
  to_workspace_id: number
  to_workspace: string
  requested_by: string | null
  created: string
  expires_at: string
  expired: boolean
}

export interface Webhook {
  id: number
  url: string
  events: string[]
  active: boolean
  secret?: string
  created: string
  last_delivery_at: string | null
  last_status: number | null
  last_error: string | null
  failures: number
}

export interface AuditEvent {
  id: number
  event_type: string
  happened_at: string
  actor_email: string | null
  actor_ip: string | null
  target_project_id: string | null
  target_user_id: number | null
  metadata: Record<string, unknown>
}

export interface MapLink {
  enabled: boolean
  token?: string
  url?: string
  ogc_enabled?: boolean
  ogc_url?: string | null
}

export interface Page<T> {
  items: T[]
  count: number
}

export interface MapLayer {
  id: string
  name: string
  type: string
  geometry: string | null
  provider: string
  packaged: boolean
  visible: boolean
  groups: string[]
}

export interface ProjectMap {
  project_id: string
  version: number
  latest_version: number
  qgis_file: string
  error: string | null
  title: string
  crs: string | null
  extent: number[] | null
  layers: MapLayer[]
  themes: Record<string, string[]>
  wms_url: string
  basemap: {
    url: string
    attribution: string
    vector_style_url: string | null
  }
}

const http = () => getHttpService()

export const PlusApi = {
  // workspaces
  createWorkspace: (data: { name: string; description?: string }) =>
    http().post('/v1/workspace', data),
  updateWorkspace: (id: number, data: { description: string }) =>
    http().patch(`/v1/workspace/${id}`, data),
  closeWorkspace: (id: number) => http().delete(`/v1/workspace/${id}`),
  workspaceUsage: (id: number) =>
    http().get<WorkspaceUsage>(`/v1/workspace/${id}/usage`),

  // members
  members: (id: number) => http().get<Member[]>(`/v2/workspaces/${id}/members`),
  updateMember: (
    id: number,
    userId: number,
    data: { workspace_role: MemberRole; reset_projects_roles?: boolean }
  ) => http().patch<Member>(`/v2/workspaces/${id}/members/${userId}`, data),
  removeMember: (id: number, userId: number) =>
    http().delete(`/v2/workspaces/${id}/members/${userId}`),

  // invitations
  invitations: (id: number) =>
    http().get<Invitation[]>(`/v2/workspaces/${id}/invitations`),
  invite: (
    id: number,
    data: {
      email: string
      role: InvitationRole
      projects?: InvitationProject[]
    }
  ) => http().post<Invitation>(`/v2/workspaces/${id}/invitations`, data),
  resendInvitation: (id: number, uuid: string) =>
    http().post<Invitation>(`/v2/workspaces/${id}/invitations/${uuid}/resend`),
  deleteInvitation: (id: number, uuid: string) =>
    http().delete(`/v2/workspaces/${id}/invitations/${uuid}`),
  myInvitations: () => http().get<Invitation[]>('/v2/invitations'),
  acceptInvitation: (uuid: string) =>
    http().post<Member>(`/v2/invitations/${uuid}/accept`),
  declineInvitation: (uuid: string) =>
    http().post(`/v2/invitations/${uuid}/decline`),
  registerFromInvitation: (
    uuid: string,
    data: { password: string; username?: string }
  ) => http().post(`/v2/invitations/${uuid}/register`, data),
  shareProject: (
    projectId: string,
    data: { email: string; role: ProjectRoleName }
  ) => http().post(`/v2/projects/${projectId}/invitations`, data),

  // transfers
  projectTransfer: (projectId: string) =>
    http().get<Transfer>(`/v2/projects/${projectId}/transfer`),
  requestTransfer: (projectId: string, workspace: string) =>
    http().post<Transfer>(`/v2/projects/${projectId}/transfer`, { workspace }),
  workspaceTransfers: (id: number) =>
    http().get<{ incoming: Transfer[]; outgoing: Transfer[] }>(
      `/v2/workspaces/${id}/transfers`
    ),
  acceptTransfer: (transferId: string, name?: string) =>
    http().post(`/v2/transfers/${transferId}/accept`, name ? { name } : {}),
  removeTransfer: (transferId: string) =>
    http().delete(`/v2/transfers/${transferId}`),

  // webhooks
  webhooks: (id: number) =>
    http().get<Webhook[]>(`/v2/workspaces/${id}/webhooks`),
  createWebhook: (id: number, data: { url: string; events: string[] }) =>
    http().post<Webhook>(`/v2/workspaces/${id}/webhooks`, data),
  updateWebhook: (
    id: number,
    webhookId: number,
    data: Partial<{ url: string; events: string[]; active: boolean }>
  ) =>
    http().patch<Webhook>(`/v2/workspaces/${id}/webhooks/${webhookId}`, data),
  deleteWebhook: (id: number, webhookId: number) =>
    http().delete(`/v2/workspaces/${id}/webhooks/${webhookId}`),
  pingWebhook: (id: number, webhookId: number) =>
    http().post<{ ok: boolean; status: number | null; error?: string }>(
      `/v2/workspaces/${id}/webhooks/${webhookId}/ping`
    ),

  // activity
  workspaceAudit: (
    id: number,
    params: { page: number; per_page: number; event_type?: string }
  ) => http().get<Page<AuditEvent>>(`/v2/workspaces/${id}/audit`, { params }),

  // web map
  projectMap: (projectId: string) =>
    http().get<ProjectMap>(`/v2/projects/${projectId}/map`),
  refreshProjectMap: (projectId: string) =>
    http().post(`/v2/projects/${projectId}/map/refresh`),
  mapLink: (projectId: string) =>
    http().get<MapLink>(`/v2/projects/${projectId}/map/link`),
  setMapLink: (
    projectId: string,
    data: { ogc_enabled?: boolean; regenerate?: boolean }
  ) => http().put<MapLink>(`/v2/projects/${projectId}/map/link`, data),
  deleteMapLink: (projectId: string) =>
    http().delete(`/v2/projects/${projectId}/map/link`)
}

/** Error message from API error response */
export function apiError(err: unknown, fallback: string): string {
  const data = (err as { response?: { data?: unknown } })?.response?.data
  if (typeof data === 'string' && data) return data
  if (data && typeof data === 'object') {
    const detail = (data as { detail?: string }).detail
    if (detail) return detail
  }
  return fallback
}

export const MEMBER_ROLES: { label: string; value: MemberRole }[] = [
  { label: 'Reader', value: 'reader' },
  { label: 'Editor', value: 'editor' },
  { label: 'Writer', value: 'writer' },
  { label: 'Admin', value: 'admin' },
  { label: 'Owner', value: 'owner' }
]

export const PROJECT_ROLES: { label: string; value: ProjectRoleName }[] = [
  { label: 'Reader', value: 'reader' },
  { label: 'Editor', value: 'editor' },
  { label: 'Writer', value: 'writer' },
  { label: 'Owner', value: 'owner' }
]
