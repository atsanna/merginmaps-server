<!--
Copyright (C) 2026 merginmaps-server contributors

SPDX-License-Identifier: AGPL-3.0-only
-->

<template>
  <app-container v-if="workspace">
    <app-section class="mb-3">
      <template #title>Members of {{ workspace.name }}</template>
      <template #headerActions>
        <PButton
          icon="ti ti-send"
          label="Invite"
          @click="inviteVisible = true"
        />
      </template>
      <PDataTable :value="members" data-key="id" :loading="loading">
        <PColumn header="User">
          <template #body="{ data }">
            <div class="flex flex-column">
              <span class="font-semibold">{{
                data.name || data.username
              }}</span>
              <span class="paragraph-p6 opacity-80">{{ data.email }}</span>
            </div>
          </template>
        </PColumn>
        <PColumn header="Role">
          <template #body="{ data }">
            <PDropdown
              :model-value="data.workspace_role"
              :options="roleOptions"
              option-label="label"
              option-value="value"
              :disabled="data.workspace_role === 'owner' && !isOwner"
              @update:model-value="(role) => changeRole(data, role)"
            />
          </template>
        </PColumn>
        <PColumn header="Type">
          <template #body="{ data }">
            <PTag
              :value="data.contributor ? 'contributor' : 'read-only'"
              :severity="data.contributor ? 'info' : 'secondary'"
            />
          </template>
        </PColumn>
        <PColumn header="Last signed in">
          <template #body="{ data }">{{
            data.last_signed_in ? $filters.datetime(data.last_signed_in) : '-'
          }}</template>
        </PColumn>
        <PColumn header="" body-class="text-right">
          <template #body="{ data }">
            <PButton
              icon="ti ti-trash"
              text
              severity="danger"
              aria-label="Remove member"
              :disabled="data.workspace_role === 'owner' && !isOwner"
              @click="remove(data)"
            />
          </template>
        </PColumn>
      </PDataTable>
      <p v-if="usage" class="p-4 paragraph-p6 opacity-80">
        Contributors: {{ usage.contributors_count }} /
        {{ usage.contributors_limit ?? 'unlimited' }}
      </p>
    </app-section>

    <app-section>
      <template #title>Invitations</template>
      <PDataTable :value="invitations" data-key="uuid">
        <template #empty>No pending invitations</template>
        <PColumn field="email" header="E-mail" />
        <PColumn header="Role">
          <template #body="{ data }">
            {{ data.role }}
            <span v-if="data.projects.length" class="paragraph-p6 opacity-80">
              ({{ data.projects.length }} project{{
                data.projects.length > 1 ? 's' : ''
              }})</span
            >
          </template>
        </PColumn>
        <PColumn header="Expires">
          <template #body="{ data }">
            <PTag v-if="data.expired" value="expired" severity="warning" />
            <span v-else>{{ $filters.datetime(data.expires_at) }}</span>
          </template>
        </PColumn>
        <PColumn header="" body-class="text-right">
          <template #body="{ data }">
            <PButton
              label="Resend"
              size="small"
              severity="secondary"
              class="mr-2"
              @click="resend(data)"
            />
            <PButton
              icon="ti ti-trash"
              text
              severity="danger"
              aria-label="Delete invitation"
              @click="removeInvitation(data)"
            />
          </template>
        </PColumn>
      </PDataTable>
    </app-section>

    <PDialog
      :visible="inviteVisible"
      @update:visible="inviteVisible = $event"
      header="Invite to workspace"
      modal
      :style="{ width: '34rem' }"
    >
      <div class="flex flex-column gap-3">
        <label for="invite-email" class="font-semibold">E-mail</label>
        <PInputText id="invite-email" v-model="inviteEmail" type="email" />
        <label for="invite-role" class="font-semibold">Role</label>
        <PDropdown
          id="invite-role"
          v-model="inviteRole"
          :options="inviteRoleOptions"
          option-label="label"
          option-value="value"
        />
        <template v-if="inviteRole === 'guest'">
          <span class="paragraph-p6 opacity-80"
            >Guests see only the projects selected here.</span
          >
          <PMultiSelect
            v-model="guestProjects"
            :options="projects"
            option-label="name"
            option-value="id"
            placeholder="Projects"
            display="chip"
          />
          <PDropdown
            v-model="guestProjectRole"
            :options="PROJECT_ROLES"
            option-label="label"
            option-value="value"
          />
        </template>
      </div>
      <template #footer>
        <PButton
          label="Cancel"
          severity="secondary"
          @click="inviteVisible = false"
        />
        <PButton
          label="Send invitation"
          :disabled="
            !inviteEmail || (inviteRole === 'guest' && !guestProjects.length)
          "
          @click="invite"
        />
      </template>
    </PDialog>
  </app-container>
</template>

<script setup lang="ts">
import {
  AppContainer,
  AppSection,
  getHttpService,
  useNotificationStore,
  useUserStore
} from '@mergin/lib'
import { computed, ref, watch } from 'vue'

import {
  Invitation,
  InvitationRole,
  MEMBER_ROLES,
  Member,
  MemberRole,
  PROJECT_ROLES,
  PlusApi,
  ProjectRoleName,
  WorkspaceUsage,
  apiError
} from '@/plus/api'

const userStore = useUserStore()
const notificationStore = useNotificationStore()

const workspace = computed(() => userStore.currentWorkspace)
const isOwner = computed(() => userStore.isWorkspaceOwner())
const members = ref<Member[]>([])
const invitations = ref<Invitation[]>([])
const usage = ref<WorkspaceUsage>()
const projects = ref<{ id: string; name: string }[]>([])
const loading = ref(false)

const roleOptions = computed(() =>
  MEMBER_ROLES.filter((r) => r.value !== 'owner' || isOwner.value)
)
const inviteRoleOptions = computed(() => [
  { label: 'Guest (selected projects)', value: 'guest' },
  ...roleOptions.value
])

const inviteVisible = ref(false)
const inviteEmail = ref('')
const inviteRole = ref<InvitationRole>('reader')
const guestProjects = ref<string[]>([])
const guestProjectRole = ref<ProjectRoleName>('reader')

async function load() {
  if (!workspace.value) return
  loading.value = true
  try {
    const id = workspace.value.id
    const [m, i, u] = await Promise.all([
      PlusApi.members(id),
      PlusApi.invitations(id),
      PlusApi.workspaceUsage(id)
    ])
    members.value = m.data
    invitations.value = i.data
    usage.value = u.data
    const p = await getHttpService().get(`/v2/workspaces/${id}/projects`, {
      params: { page: 1, per_page: 100 }
    })
    projects.value = p.data.items ?? []
  } catch (err) {
    notificationStore.error({ text: apiError(err, 'Failed to load members') })
  } finally {
    loading.value = false
  }
}

watch(workspace, load, { immediate: true })

async function changeRole(member: Member, role: MemberRole) {
  try {
    await PlusApi.updateMember(workspace.value.id, member.id, {
      workspace_role: role
    })
    await load()
  } catch (err) {
    notificationStore.error({ text: apiError(err, 'Failed to change role') })
  }
}

async function remove(member: Member) {
  if (!confirm(`Remove ${member.email} from the workspace?`)) return
  try {
    await PlusApi.removeMember(workspace.value.id, member.id)
    await load()
  } catch (err) {
    notificationStore.error({ text: apiError(err, 'Failed to remove member') })
  }
}

async function invite() {
  try {
    await PlusApi.invite(workspace.value.id, {
      email: inviteEmail.value.trim(),
      role: inviteRole.value,
      projects:
        inviteRole.value === 'guest'
          ? guestProjects.value.map((id) => ({
              id,
              role: guestProjectRole.value
            }))
          : undefined
    })
    inviteVisible.value = false
    notificationStore.show({ text: `Invitation sent to ${inviteEmail.value}` })
    inviteEmail.value = ''
    guestProjects.value = []
    await load()
  } catch (err) {
    notificationStore.error({
      text: apiError(err, 'Failed to send invitation')
    })
  }
}

async function resend(inv: Invitation) {
  try {
    await PlusApi.resendInvitation(workspace.value.id, inv.uuid)
    notificationStore.show({ text: `Invitation sent again to ${inv.email}` })
    await load()
  } catch (err) {
    notificationStore.error({
      text: apiError(err, 'Failed to resend invitation')
    })
  }
}

async function removeInvitation(inv: Invitation) {
  try {
    await PlusApi.deleteInvitation(workspace.value.id, inv.uuid)
    await load()
  } catch (err) {
    notificationStore.error({
      text: apiError(err, 'Failed to delete invitation')
    })
  }
}
</script>
