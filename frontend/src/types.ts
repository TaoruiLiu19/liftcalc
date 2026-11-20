export type MainHook = { mass_t: number; rated_t: number; is_default: number }
export type Model = { brand: string; model: string; config: string; hook_main_t: number | null; main_hooks: MainHook[] }
export type Snapshot = {
  id: string
  svg: string | null
  scale: number | null
  warnings: string[]
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
export interface Api {
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
