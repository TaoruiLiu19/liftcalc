export type HeightDatum = 'top' | 'bottom' | 'estimate'
export type RiggingMeasurement = { datum: HeightDatum; value: number | null }

export function riggingRise(measurement: RiggingMeasurement, bodyHeight: number) {
  if (measurement.datum === 'estimate' || !Number.isFinite(measurement.value)) return null
  return measurement.value! - (measurement.datum === 'bottom' ? bodyHeight : 0)
}
