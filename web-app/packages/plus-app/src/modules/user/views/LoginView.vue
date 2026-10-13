<!--
Copyright (C) Lutra Consulting Limited

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-MerginMaps-Commercial
-->

<template>
  <login-view-template @userLogin="handleUserLogin">
    <template v-if="configData?.sso_enabled" #additionalButtons>
      <div class="flex flex-column gap-2 mt-3">
        <template v-if="ssoOpen">
          <PInputText
            v-model="ssoEmail"
            type="email"
            placeholder="Your work e-mail"
            @keyup.enter="ssoLogin"
          />
          <small v-if="ssoError" class="p-error">{{ ssoError }}</small>
          <PButton
            label="Continue"
            :disabled="!ssoEmail.includes('@')"
            @click="ssoLogin"
          />
        </template>
        <PButton
          v-else
          label="Continue with SSO"
          severity="secondary"
          icon="ti ti-key"
          @click="ssoOpen = true"
        />
      </div>
    </template>
  </login-view-template>
</template>

<script lang="ts">
import {
  LoginViewTemplate,
  getHttpService,
  useInstanceStore,
  useUserStore
} from '@mergin/lib'
import { mapActions, mapState } from 'pinia'
import { defineComponent } from 'vue'

export default defineComponent({
  name: 'LoginView',
  components: {
    LoginViewTemplate
  },
  data() {
    return {
      ssoOpen: false,
      ssoEmail: '',
      ssoError: ''
    }
  },
  computed: {
    ...mapState(useInstanceStore, ['configData'])
  },
  methods: {
    ...mapActions(useUserStore, [
      'userLogin',
      'redirectAfterLogin',
      'redirectFromLoginAfterLogin'
    ]),
    async handleUserLogin(payload) {
      try {
        await this.userLogin(payload)
        if (payload.currentRoute.query.redirect) {
          await this.redirectAfterLogin({
            currentRoute: payload.currentRoute
          })
        } else {
          await this.redirectFromLoginAfterLogin({
            currentRoute: payload.currentRoute
          })
        }
      } catch (err) {
        console.error(err)
      }
    },
    async ssoLogin() {
      this.ssoError = ''
      const email = this.ssoEmail.trim()
      try {
        // check the e-mail domain has an SSO connection before leaving the page
        await getHttpService().get('/v2/sso/connections', {
          params: { email }
        })
      } catch {
        this.ssoError = 'Single sign-on is not set up for this e-mail domain'
        return
      }
      const next = (this.$route.query.redirect as string) || '/dashboard'
      window.location.href = `/v2/sso/login?${new URLSearchParams({
        email,
        next
      })}`
    }
  }
})
</script>
