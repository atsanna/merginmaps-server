// Copyright (C) 2026 merginmaps-server contributors
//
// SPDX-License-Identifier: AGPL-3.0-only

import { defineStore } from 'pinia'

import { Invitation, PlusApi } from '@/plus/api'

export const usePlusStore = defineStore('plusModule', {
  state: () => ({
    invitations: [] as Invitation[]
  }),
  actions: {
    async fetchInvitations() {
      try {
        const resp = await PlusApi.myInvitations()
        this.invitations = resp.data
      } catch {
        this.invitations = []
      }
    }
  }
})
