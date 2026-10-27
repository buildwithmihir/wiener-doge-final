import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import type { ChartRange, ChartResponse, Market } from './types'

/** Open markets plus paused ones (paused stay visible, with betting disabled). */
export function useMarkets() {
  return useQuery({
    queryKey: ['markets'],
    refetchInterval: 30_000,
    queryFn: async (): Promise<Market[]> => {
      const [open, paused] = await Promise.all([
        api<{ items: Market[] }>('/markets?status=open&limit=100'),
        api<{ items: Market[] }>('/markets?status=paused&limit=100'),
      ])
      return [...open.items, ...paused.items]
    },
  })
}

export function useChart(symbol: string, range: ChartRange) {
  return useQuery({
    queryKey: ['chart', symbol, range],
    refetchInterval: 60_000,
    queryFn: () => api<ChartResponse>(`/assets/${encodeURIComponent(symbol)}/chart?range=${range}`),
  })
}

import type { AssetRow } from './types'

export function useAssets() {
  return useQuery({
    queryKey: ['assets'],
    refetchInterval: 30_000,
    queryFn: async () => (await api<{ items: AssetRow[] }>('/assets')).items,
  })
}