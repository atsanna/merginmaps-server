<!--
Copyright (C) 2026 merginmaps-server contributors

SPDX-License-Identifier: AGPL-3.0-only
-->

<template>
  <div class="flex justify-content-center p-4">
    <app-section class="w-full" :style="{ maxWidth: '32rem' }">
      <template #title>Workspace invitation</template>
      <div class="p-4 flex flex-column gap-3">
        <template v-if="userStore.isLoggedIn">
          <template v-if="invitation">
            <p>
              <b>{{ invitation.inviter }}</b> invited you to the workspace
              <b>{{ invitation.workspace }}</b> as <b>{{ invitation.role }}</b
              >.
            </p>
            <div class="flex gap-2">
              <PButton label="Accept" @click="accept" />
              <PButton label="Decline" severity="secondary" @click="decline" />
            </div>
          </template>
          <p v-else-if="loaded">
            This invitation is not valid for {{ userStore.loggedUser?.email }}:
            it may be expired, already used or sent to another e-mail address.
          </p>
        </template>
        <template v-else>
          <p>
            Create your account to join the workspace. Already have an account?
            <router-link :to="loginLink">Sign in</router-link> to accept the
            invitation.
          </p>
          <label for="inv-username" class="font-semibold"
            >Username (optional)</label
          >
          <PInputText id="inv-username" v-model="username" />
          <label for="inv-password" class="font-semibold">Password</label>
          <PPassword
            id="inv-password"
            v-model="password"
            toggle-mask
            :feedback="false"
            input-class="w-full"
          />
          <label for="inv-confirm" class="font-semibold"
            >Confirm password</label
          >
          <PPassword
            id="inv-confirm"
            v-model="confirm"
            toggle-mask
            :feedback="false"
            input-class="w-full"
          />
          <small v-if="errors" class="p-error">{{ errors }}</small>
          <PButton
            label="Create account"
            :disabled="!password || password !== confirm"
            @click="register"
          />
        </template>
      </div>
    </app-section>
  </div>
</template>

<script setup lang="ts">
import { AppSection, useNotificationStore, useUserStore } from '@mergin/lib'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { Invitation, PlusApi, apiError } from '@/plus/api'

const props = defineProps<{ uuid: string }>()
const userStore = useUserStore()
const notificationStore = useNotificationStore()
const router = useRouter()

const invitation = ref<Invitation>()
const loaded = ref(false)
const username = ref('')
const password = ref('')
const confirm = ref('')
const errors = ref('')
const loginLink = computed(() => ({
  path: '/login',
  query: { redirect: `/invitations/${props.uuid}` }
}))

onMounted(async () => {
  if (!userStore.isLoggedIn) return
  try {
    const resp = await PlusApi.myInvitations()
    invitation.value = resp.data.find((i) => i.uuid === props.uuid)
  } catch {
    // shown as not valid invitation
  } finally {
    loaded.value = true
  }
})

async function accept() {
  try {
    await PlusApi.acceptInvitation(props.uuid)
    await userStore.getWorkspaces()
    await userStore.setWorkspace({ workspaceId: invitation.value.workspace_id })
    notificationStore.show({
      text: `You joined workspace ${invitation.value.workspace}`
    })
    await router.push({ path: '/dashboard' })
  } catch (err) {
    notificationStore.error({
      text: apiError(err, 'Failed to accept invitation')
    })
  }
}

async function decline() {
  try {
    await PlusApi.declineInvitation(props.uuid)
    await router.push({ path: '/dashboard' })
  } catch (err) {
    notificationStore.error({
      text: apiError(err, 'Failed to decline invitation')
    })
  }
}

async function register() {
  errors.value = ''
  try {
    await PlusApi.registerFromInvitation(props.uuid, {
      password: password.value,
      username: username.value.trim() || undefined
    })
    notificationStore.show({
      text: 'Your account has been created, you can sign in now'
    })
    await router.push({ path: '/login' })
  } catch (err) {
    const data = (err as { response?: { data?: Record<string, string[]> } })
      ?.response?.data
    errors.value =
      data && typeof data === 'object' && !('detail' in data)
        ? Object.values(data).flat().join(' ')
        : apiError(err, 'Failed to create account')
  }
}
</script>
