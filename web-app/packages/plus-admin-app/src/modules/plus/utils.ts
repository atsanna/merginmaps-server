// Copyright (C) 2026 merginmaps-server contributors
//
// SPDX-License-Identifier: AGPL-3.0-only

export const BYTES_IN_GB = 1024 * 1024 * 1024

const UNITS = ['B', 'kB', 'MB', 'GB', 'TB', 'PB']

/** Human readable size of bytes value, e.g. 1.50 GB */
export function formatBytes(value: number | null | undefined, digits = 2) {
  if (value === null || value === undefined || isNaN(value)) return '-'
  if (value <= 0) return '0 B'
  const exponent = Math.min(
    Math.floor(Math.log(value) / Math.log(1024)),
    UNITS.length - 1
  )
  const scaled = value / Math.pow(1024, exponent)
  return `${exponent === 0 ? scaled : scaled.toFixed(digits)} ${
    UNITS[exponent]
  }`
}

export function bytesToGb(value: number | null | undefined): number | null {
  if (value === null || value === undefined) return null
  return Math.round((value / BYTES_IN_GB) * 100) / 100
}

export function gbToBytes(value: number): number {
  return Math.round(value * BYTES_IN_GB)
}

/** Percentage of used storage, capped at 100 */
export function usagePercent(used: number, limit: number): number {
  if (!limit) return used > 0 ? 100 : 0
  return Math.min(100, Math.round((used / limit) * 100))
}
