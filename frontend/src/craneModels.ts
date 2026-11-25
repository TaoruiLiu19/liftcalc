import type { Model } from './types'

export const craneModelKey = (row: Pick<Model, 'brand' | 'model'>) => JSON.stringify([row.brand, row.model])

export function groupCraneModels(rows: Model[]) {
  const groups = new Map<string, {
    key: string
    brand: string
    model: string
    tonnage: number
    configs: {index: number; row: Model}[]
  }>()
  rows.forEach((row, index) => {
    const key = craneModelKey(row)
    const config = {index, row}
    const group = groups.get(key)
    if (group) group.configs.push(config)
    else groups.set(key, {key, brand:row.brand, model:row.model, tonnage:row.tonnage_class_t, configs:[config]})
  })
  return [...groups.values()].sort((a,b) => a.tonnage-b.tonnage)
}
