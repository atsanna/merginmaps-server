// Copyright (C) Lutra Consulting Limited
//
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-MerginMaps-Commercial

import {
  AccountUnlockView,
  ChangePasswordView,
  FileBrowserView,
  FileVersionDetailView,
  ProjectVersionsView,
  NotFoundView,
  VerifyEmailView,
  routeUtils,
  useUserStore,
  ProjectRouteName,
  UserRouteName,
  DashboardRouteName,
  getDashboardTitle,
  getUserTitle,
  getProjectTitle
} from '@mergin/lib'
import { Pinia } from 'pinia'
import {
  createWebHistory,
  createRouter as createRouterInstance
} from 'vue-router'

import DashboardView from '@/modules/dashboard/views/DashboardView.vue'
import AppHeader from '@/modules/layout/components/AppHeader.vue'
import ProjectCollaboratorsView from '@/modules/project/views/ProjectCollaboratorsView.vue'
import ProjectSettingsView from '@/modules/project/views/ProjectSettingsView.vue'
import ProjectsListView from '@/modules/project/views/ProjectsListView.vue'
import ProjectView from '@/modules/project/views/ProjectView.vue'
import LoginView from '@/modules/user/views/LoginView.vue'
import ProfileView from '@/modules/user/views/ProfileView.vue'
import PlusSideBar from '@/plus/components/PlusSideBar.vue'
import InvitationView from '@/plus/views/InvitationView.vue'
import ProjectMapView from '@/plus/views/ProjectMapView.vue'
import WorkspaceMembersView from '@/plus/views/WorkspaceMembersView.vue'
import WorkspaceSettingsView from '@/plus/views/WorkspaceSettingsView.vue'
import WorkspacesView from '@/plus/views/WorkspacesView.vue'

export const PLUS_MAP_ROUTE = 'plus-project-map'
const SideBar = PlusSideBar

export const createRouter = (pinia: Pinia) => {
  const router = createRouterInstance({
    history: createWebHistory(),
    routes: [
      {
        path: '/',
        name: 'home',
        meta: { public: true },
        redirect: null,
        beforeEnter: (to, from, next) => {
          const userStore = useUserStore(pinia)
          if (userStore.isLoggedIn) {
            next('/dashboard')
          } else {
            next('/login')
          }
        }
      },
      {
        beforeEnter: (to, from, next) => {
          const userStore = useUserStore(pinia)
          if (userStore.isLoggedIn) {
            next('/dashboard')
          } else {
            next()
          }
        },
        path: '/login/:reset?',
        name: UserRouteName.Login,
        component: LoginView,
        props: true,
        meta: { public: true }
      },
      {
        path: '/confirm-email/:token',
        name: UserRouteName.ConfirmEmail,
        component: VerifyEmailView,
        props: true,
        meta: { public: true }
      },
      {
        path: '/change-password/:token',
        name: UserRouteName.ChangePassword,
        component: ChangePasswordView,
        props: true,
        meta: { public: true }
      },
      {
        path: '/unlock-account/:token',
        name: UserRouteName.UnlockAccount,
        component: AccountUnlockView,
        props: true,
        meta: { public: true }
      },
      {
        path: '/dashboard',
        name: DashboardRouteName.Dashboard,
        components: {
          default: DashboardView,
          header: AppHeader,
          sidebar: SideBar
        },
        meta: {
          breadcrump: [{ title: 'Dashboard', path: '/dashboard' }]
        },
        props: {
          default: true
        }
      },
      {
        path: '/profile',
        name: UserRouteName.UserProfile,
        meta: {
          allowedForNoWorkspace: true,
          breadcrump: [{ title: 'Profile', path: '/profile' }]
        },
        components: {
          default: ProfileView,
          header: AppHeader,
          sidebar: SideBar
        },
        props: true
      },
      {
        path: '/projects',
        name: ProjectRouteName.Projects,
        components: {
          default: ProjectsListView,
          header: AppHeader,
          sidebar: SideBar
        },
        props: {
          default: true
        },
        meta: {
          public: true,
          breadcrump: [{ title: 'Projects', path: '/projects' }]
        },
        children: [
          {
            path: 'explore',
            name: ProjectRouteName.ProjectsExplore,
            component: ProjectsListView,
            props: true,
            meta: {
              public: true,
              breadcrump: [
                { title: 'Public projects', path: '/projects/explore' }
              ]
            }
          },
          {
            path: ':namespace',
            name: 'namespace-projects',
            component: ProjectsListView,
            props: true
          }
        ]
      },
      /** Redirect of unused /blob path to /tree */
      {
        path: '/projects/:namespace/:projectName/blob/:location?',
        name: 'blob',
        component: NotFoundView,
        props: true,
        meta: { public: true },
        beforeEnter: (to, from, next) => {
          next({
            path: `/projects/${to.params.namespace}/${
              to.params.projectName
            }/tree${from.params.location ? `/${from.params.location}` : ''}`,
            query: { file_path: to.params.location }
          })
        }
      },
      /** Redirect of unused /history/:version_id path to /history?version_id */
      {
        path: '/projects/:namespace/:projectName/history/:version_id',
        name: 'project-versions-detail',
        component: NotFoundView,
        props: true,
        meta: { public: true },
        beforeEnter: (to, from, next) => {
          next({
            path: `/projects/${to.params.namespace}/${to.params.projectName}/history`,
            query: { version_id: to.params.version_id }
          })
        }
      },
      {
        path: '/projects/:namespace/:projectName',
        name: 'project',
        components: {
          default: ProjectView,
          header: AppHeader,
          sidebar: SideBar
        },
        props: {
          default: true
        },
        meta: {
          breadcrump: [{ title: 'Projects', path: '/projects' }]
        },
        redirect: { name: ProjectRouteName.ProjectTree },

        children: [
          {
            path: 'tree/:location(.*)?',
            name: ProjectRouteName.ProjectTree,
            component: FileBrowserView,
            props: true,
            meta: {
              public: true,
              breadcrump: (route) => [
                {
                  title: route.params?.projectName,
                  path: `/projects/${route.params.namespace}/${route.params.projectName}/tree`
                }
              ]
            }
          },
          {
            path: 'settings',
            name: 'project-settings',
            component: ProjectSettingsView,
            props: true,
            meta: {
              breadcrump: (route) => [
                {
                  title: route.params?.projectName,
                  path: `/projects/${route.params.namespace}/${route.params.projectName}/tree`
                }
              ]
            }
          },
          {
            path: 'history',
            name: 'project-versions',
            component: ProjectVersionsView,
            props: true,
            meta: {
              breadcrump: (route) => [
                {
                  title: route.params?.projectName,
                  path: `/projects/${route.params.namespace}/${route.params.projectName}/tree`
                }
              ]
            }
          },
          {
            path: 'collaborators',
            name: ProjectRouteName.ProjectCollaborators,
            component: ProjectCollaboratorsView,
            props: true,
            meta: {
              breadcrump: (route) => [
                {
                  title: route.params?.projectName,
                  path: `/projects/${route.params.namespace}/${route.params.projectName}/tree`
                }
              ]
            }
          },
          {
            path: 'map',
            name: PLUS_MAP_ROUTE,
            component: ProjectMapView,
            props: true,
            meta: {
              breadcrump: (route) => [
                {
                  title: route.params?.projectName,
                  path: `/projects/${route.params.namespace}/${route.params.projectName}/tree`
                }
              ]
            }
          },
          {
            path: 'history/:version_id/:path',
            name: ProjectRouteName.FileVersionDetail,
            component: FileVersionDetailView,
            props: true,
            meta: {
              public: true,
              breadcrump: (route) => [
                {
                  title: route.params?.projectName,
                  path: `/projects/${route.params.namespace}/${route.params.projectName}/tree`
                },
                {
                  title: route.params?.version_id,
                  path: `/projects/${route.params.namespace}/${route.params.projectName}/history/${route.params.version_id}`
                },
                {
                  title: route.params?.path,
                  path: route.fullPath
                }
              ]
            }
          }
        ]
      },
      // enterprise add-on pages
      {
        path: '/workspaces',
        name: 'plus-workspaces',
        components: {
          default: WorkspacesView,
          header: AppHeader,
          sidebar: SideBar
        },
        meta: {
          allowedForNoWorkspace: true,
          breadcrump: [{ title: 'Workspaces', path: '/workspaces' }]
        }
      },
      {
        path: '/workspace/members',
        name: 'plus-workspace-members',
        components: {
          default: WorkspaceMembersView,
          header: AppHeader,
          sidebar: SideBar
        },
        meta: {
          breadcrump: [{ title: 'Members', path: '/workspace/members' }]
        }
      },
      {
        path: '/workspace/settings',
        name: 'plus-workspace-settings',
        components: {
          default: WorkspaceSettingsView,
          header: AppHeader,
          sidebar: SideBar
        },
        meta: {
          breadcrump: [
            { title: 'Workspace settings', path: '/workspace/settings' }
          ]
        }
      },
      {
        // link of transfer e-mails: switch to the target workspace first
        path: '/workspaces/:id/transfers',
        name: 'plus-workspace-transfers',
        component: NotFoundView,
        beforeEnter: async (to) => {
          const userStore = useUserStore(pinia)
          const id = Number(to.params.id)
          if (userStore.isLoggedIn && userStore.getWorkspaceById({ id })) {
            await userStore.setWorkspace({ workspaceId: id })
          }
          return { path: '/workspace/settings', query: { tab: 'transfers' } }
        }
      },
      {
        // public shared map, also embeddable in an iframe
        path: '/maps/:token',
        name: 'plus-shared-map',
        component: ProjectMapView,
        props: true,
        meta: { public: true, allowedForNoWorkspace: true }
      },
      {
        path: '/invitations/:uuid',
        name: 'plus-invitation',
        component: InvitationView,
        props: true,
        meta: { public: true, allowedForNoWorkspace: true }
      },
      {
        path: '/:pathMatch(.*)*',
        component: NotFoundView,
        meta: { public: true }
      }
    ]
  })

  /** Selects current workspace (last used, preferred or first one) once the user is signed in. */
  let workspaceCheckedFor: number | undefined
  router.beforeEach(async (to, from, next) => {
    const userStore = useUserStore(pinia)
    const userId = userStore.loggedUser?.id
    // once per signed in user (users without workspaces would otherwise reload them on every page)
    if (
      userStore.isLoggedIn &&
      !userStore.currentWorkspace &&
      userId !== undefined &&
      workspaceCheckedFor !== userId
    ) {
      workspaceCheckedFor = userId
      await userStore.checkCurrentWorkspace()
    }
    next()
  })

  /** Handles redirect to /login when user is not authenticated. */
  router.beforeEach((to, from, next) => {
    const userStore = useUserStore(pinia)
    routeUtils.isAuthenticatedGuard(to, from, next, userStore)
  })

  router.beforeEach(async (to, from, next) => {
    const titleResolvers = [getProjectTitle, getUserTitle, getDashboardTitle]

    // Use `find` to get the first resolved title
    to.meta.title = (route) => {
      return titleResolvers
        .map((resolver) => resolver(route))
        .find((title) => title)
    }

    next()
  })
  return router
}
