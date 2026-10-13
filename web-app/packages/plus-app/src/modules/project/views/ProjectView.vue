<!--
Copyright (C) Lutra Consulting Limited

SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-MerginMaps-Commercial
-->

<template>
  <project-view-template
    :show-namespace="false"
    :namespace="namespace"
    :projectName="projectName"
    :show-settings="isProjectOwner"
    :hide-clone-button="!canCreateProject"
    :map-route="PLUS_MAP_ROUTE"
    @open-clone-dialog="openCloneDialog"
    @open-share-dialog="openShareDialog"
  >
    <template v-if="configData?.maps_enabled" #map.tab>
      <PTabPanel header="Map" />
    </template>
  </project-view-template>
</template>

<script lang="ts">
import {
  CloneDialog,
  ProjectShareDialog,
  ProjectViewTemplate,
  useDialogStore,
  useFormStore,
  useInstanceStore,
  useProjectStore,
  useUserStore
} from '@mergin/lib'
import { computed, defineComponent } from 'vue'

import { PLUS_MAP_ROUTE } from '@/router'

export default defineComponent({
  name: 'ProjectView',
  components: {
    ProjectViewTemplate
  },
  props: {
    namespace: String,
    projectName: String
  },
  setup(props) {
    const userStore = useUserStore()
    const projectStore = useProjectStore()
    const dialogStore = useDialogStore()
    const formStore = useFormStore()
    const instanceStore = useInstanceStore()
    const configData = computed(() => instanceStore.configData)

    const canCreateProject = computed(() => userStore.isWorkspaceAdmin())
    const isProjectOwner = computed(() => projectStore.isProjectOwner)

    function openCloneDialog() {
      const dialogProps = {
        namespace: props.namespace,
        project: props.projectName
      }
      const dialog = {
        maxWidth: 580,
        persistent: true,
        header: 'Clone project'
      }
      const listeners = {
        error: (error, data) => {
          formStore.handleError({
            componentId: data.merginComponentUuid,
            error,
            generalMessage: 'Failed to clone project'
          })
        }
      }
      dialogStore.show({
        component: CloneDialog,
        params: {
          props: dialogProps,
          listeners,
          dialog
        }
      })
    }

    function openShareDialog() {
      const dialog = {
        maxWidth: 600,
        header: 'Share project'
      }
      dialogStore.show({
        component: ProjectShareDialog,
        params: {
          dialog
        }
      })
    }

    return {
      PLUS_MAP_ROUTE,
      configData,
      canCreateProject,
      isProjectOwner,
      openCloneDialog,
      openShareDialog
    }
  }
})
</script>
