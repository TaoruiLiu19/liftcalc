export type MainHook = { mass_t: number; rated_t: number; is_default: number }
export type Model = { brand: string; model: string; config: string; booms: number[]; hook_main_t: number | null; main_hooks: MainHook[] }
export type Sling = {
  index: number
  name: string
  x: number
  y: number
  run: number
  length: number
  angle_deg: number
  share: number
  force_t: number
  equilibrium_min_kn: number
  equilibrium_max_kn: number
}
export type LoadSummary = {
  length_m: number
  width_m: number
  height_m: number
  clearance_m: number
  weight_t: number
  cg: { x: number; y: number; z: number }
  lug_inset_m: number
  sling_height_m: number
  sling_height_derived: boolean
  slings: Sling[]
  max_force_t: number
  min_force_t: number
  max_angle_deg: number
  min_angle_deg: number
  required_lift_height_m: number
  hook_height_m: number
  height_source: string
  notes: string[]
}
export type Snapshot = {
  id: string
  svg: string | null
  scale: number | null
  warnings: string[]
  load: LoadSummary | null
  cap: {
    model: string
    config: string | null
    status: string
    explanation: string
    required: number
    hook_mass: number
    hook_rated_t: number | null
    rated_load: number | null
    boom_len: number | null
    lift_height: number | null
    max_radius: number | null
    utilization: number | null
  }
}
export type TransferResult = {
  clearance: { lower_m: number; pair: string; leg: number; start: number; end: number }
  poses: number[][]
  stations: {center: number[]; heading: number}[]
  drawings: { id: string; svg: string }[]
  shares: number[]
  loads: number[]
  segments: { leg: number; start: number; end: number; radii: [number, number][]; ratios: (number | null)[]; unsafe: string[]; unknown: string[] }[]
}
export interface Api {
  calculate(input: { kind: 'rail.transfer'; transfer: unknown }): Promise<TransferResult>
  models(): Promise<Model[]>
  calculate(input: Record<string, unknown>): Promise<Snapshot>
  dxf(id: string): Promise<string>
  export(id: string, fmt: string): Promise<boolean>
}
declare global {
  interface Window {
    pywebview?: { api: Api }
  }
}
