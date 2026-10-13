<!--
Copyright (C) 2026 merginmaps-server contributors

SPDX-License-Identifier: AGPL-3.0-only
-->

<template>
  <app-container>
    <app-section v-if="notReady" class="p-4">
      <p class="mb-3">
        The map of this project is not available yet. It is prepared after every
        push of a project with a QGIS project file; only layers with data stored
        in the project (GeoPackage, Shapefile, GeoTIFF, MBTiles) are shown.
      </p>
      <PButton
        v-if="canRefresh"
        label="Prepare map now"
        severity="secondary"
        @click="refresh"
      />
    </app-section>
    <div v-else class="grid">
      <div class="col-12 lg:col-9">
        <div
          ref="mapElement"
          class="plus-map border-round-xl overflow-hidden"
        />
        <p v-if="config?.error" class="paragraph-p6 text-orange-600 mt-2">
          The latest version could not be processed ({{ config.error }}), the
          map shows version v{{ config.version }}.
        </p>
      </div>
      <div class="col-12 lg:col-3 flex flex-column gap-3">
        <app-section v-if="themeNames.length">
          <template #title>Map themes</template>
          <div class="px-4 pb-4">
            <PDropdown
              v-model="theme"
              :options="themeNames"
              placeholder="Choose theme"
              show-clear
              class="w-full"
            />
          </div>
        </app-section>
        <app-section>
          <template #title>Layers</template>
          <div class="px-4 pb-4 flex flex-column gap-2">
            <div
              v-for="layer in config?.layers ?? []"
              :key="layer.id"
              class="flex flex-column"
            >
              <div class="flex align-items-center gap-2">
                <PCheckbox
                  v-model="visible"
                  :input-id="layer.id"
                  :value="layer.id"
                  :disabled="!layer.packaged"
                />
                <label
                  :for="layer.id"
                  :class="{ 'opacity-50': !layer.packaged }"
                  >{{ layer.name }}
                  <i
                    v-if="!layer.packaged"
                    v-tooltip="'Data are not part of the project'"
                    class="ti ti-cloud-off"
                  ></i
                ></label>
              </div>
              <img
                v-if="layer.packaged && visible.includes(layer.id)"
                :src="legendUrl(layer.name)"
                :alt="`Legend of ${layer.name}`"
                class="ml-5 mt-1"
                loading="lazy"
              />
            </div>
          </div>
        </app-section>
        <app-section v-if="featureInfo.length">
          <template #title>Feature</template>
          <div class="px-4 pb-4">
            <div v-for="(feature, i) in featureInfo" :key="i" class="mb-3">
              <p class="font-semibold mb-1">{{ feature.layer }}</p>
              <table class="paragraph-p6">
                <tr v-for="(value, key) in feature.properties" :key="key">
                  <td class="pr-2 opacity-80">{{ key }}</td>
                  <td>{{ value }}</td>
                </tr>
              </table>
            </div>
          </div>
        </app-section>
      </div>
    </div>
  </app-container>
</template>

<script setup lang="ts">
import {
  AppContainer,
  AppSection,
  getHttpService,
  useNotificationStore,
  useProjectStore
} from '@mergin/lib'
import WMSCapabilities from 'ol/format/WMSCapabilities'
import ImageLayer from 'ol/layer/Image'
import TileLayer from 'ol/layer/Tile'
import OlMap from 'ol/Map'
import { transformExtent } from 'ol/proj'
import ImageWMS from 'ol/source/ImageWMS'
import XYZ from 'ol/source/XYZ'
import View from 'ol/View'
import 'ol/ol.css'
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { PlusApi, ProjectMap, apiError } from '@/plus/api'

const projectStore = useProjectStore()
const notificationStore = useNotificationStore()

const mapElement = ref<HTMLElement>()
const config = ref<ProjectMap>()
const notReady = ref(false)
const visible = ref<string[]>([])
const theme = ref<string>()
const featureInfo = ref<{ layer: string; properties: object }[]>([])
const canRefresh = computed(() => projectStore.isProjectOwner)
const themeNames = computed(() => Object.keys(config.value?.themes ?? {}))

let map: OlMap | undefined
let wmsSource: ImageWMS | undefined
let poll: number | undefined

const wmsUrl = computed(() =>
  config.value ? `${window.location.origin}${config.value.wms_url}` : ''
)

function layerNames(ids: string[]) {
  // QGIS draws LAYERS from bottom to top, the layer list goes from top
  return (config.value?.layers ?? [])
    .filter((l) => l.packaged && ids.includes(l.id))
    .map((l) => l.name)
    .reverse()
}

function legendUrl(name: string) {
  const params = new URLSearchParams({
    SERVICE: 'WMS',
    VERSION: '1.3.0',
    REQUEST: 'GetLegendGraphic',
    FORMAT: 'image/png',
    LAYER: name,
    LAYERTITLE: 'false'
  })
  return `${config.value.wms_url}?${params}`
}

async function fitToProject() {
  const cfg = config.value
  const view = map.getView()
  if (cfg.extent && (cfg.crs === 'EPSG:3857' || cfg.crs === 'EPSG:4326')) {
    view.fit(transformExtent(cfg.extent, cfg.crs, 'EPSG:3857'))
    return
  }
  // other CRSs: use the WGS84 bounding box advertised by QGIS Server
  try {
    const resp = await getHttpService().get(cfg.wms_url, {
      params: { SERVICE: 'WMS', VERSION: '1.3.0', REQUEST: 'GetCapabilities' },
      responseType: 'text'
    })
    const caps = new WMSCapabilities().read(resp.data)
    const bbox = caps?.Capability?.Layer?.EX_GeographicBoundingBox
    if (bbox) view.fit(transformExtent(bbox, 'EPSG:4326', 'EPSG:3857'))
  } catch {
    // keep world view
  }
}

function createMap() {
  const cfg = config.value
  wmsSource = new ImageWMS({
    url: wmsUrl.value,
    params: {
      LAYERS: layerNames(visible.value).join(','),
      FORMAT: 'image/png',
      TRANSPARENT: true,
      VERSION: '1.3.0',
      _v: cfg.version
    },
    serverType: 'qgis',
    crossOrigin: 'use-credentials'
  })
  map = new OlMap({
    target: mapElement.value,
    layers: [
      new TileLayer({
        source: new XYZ({
          url: cfg.basemap.url,
          attributions: cfg.basemap.attribution
        })
      }),
      new ImageLayer({ source: wmsSource })
    ],
    view: new View({ center: [0, 0], zoom: 2 })
  })
  map.on('singleclick', async (evt) => {
    const queryLayers = layerNames(visible.value)
    if (!queryLayers.length) return
    const url = wmsSource.getFeatureInfoUrl(
      evt.coordinate,
      map.getView().getResolution(),
      'EPSG:3857',
      {
        INFO_FORMAT: 'application/json',
        QUERY_LAYERS: queryLayers.join(','),
        FEATURE_COUNT: 5,
        FI_POINT_TOLERANCE: 10
      }
    )
    try {
      const resp = await getHttpService().get(url)
      featureInfo.value = (resp.data?.features ?? []).map((f) => ({
        layer: String(f.id ?? '').split('.')[0],
        properties: f.properties
      }))
    } catch {
      featureInfo.value = []
    }
  })
  fitToProject()
}

async function load() {
  const projectId = projectStore.project?.id
  if (!projectId) return
  try {
    const resp = await PlusApi.projectMap(projectId)
    const first = !config.value
    const changed = config.value && config.value.version !== resp.data.version
    config.value = resp.data
    notReady.value = false
    if (first) {
      visible.value = resp.data.layers
        .filter((l) => l.packaged && l.visible)
        .map((l) => l.id)
      // wait for the map element to be rendered
      setTimeout(createMap)
    } else if (changed) {
      wmsSource?.updateParams({ _v: resp.data.version })
    }
  } catch (err) {
    if ((err as { response?: { status?: number } })?.response?.status === 404) {
      notReady.value = true
    } else {
      notificationStore.error({ text: apiError(err, 'Failed to load map') })
    }
  }
}

async function refresh() {
  try {
    await PlusApi.refreshProjectMap(projectStore.project.id)
    notificationStore.show({ text: 'The map is being prepared' })
  } catch (err) {
    notificationStore.error({ text: apiError(err, 'Failed to prepare map') })
  }
}

watch(
  () => projectStore.project?.id,
  () => {
    load()
    window.clearInterval(poll)
    // the map follows new project versions
    poll = window.setInterval(load, 60000)
  },
  { immediate: true }
)

watch(visible, (ids) => {
  wmsSource?.updateParams({ LAYERS: layerNames(ids).join(',') })
})

watch(theme, (name) => {
  if (!name) return
  visible.value = [...(config.value.themes[name] ?? [])]
})

onBeforeUnmount(() => {
  window.clearInterval(poll)
  map?.setTarget(undefined)
})
</script>

<style scoped>
.plus-map {
  width: 100%;
  height: 70vh;
  min-height: 360px;
}
</style>
