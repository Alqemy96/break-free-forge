/**
 * Workbench history: a stack of identify payloads (the last one is the current serial), plus one
 * pending transform waiting for "Use this" or "Discard". Pure reducer, unit-tested.
 */
import type { DiffRow, IdentifyResponse, TransformResponse } from '@/api/types'

export interface HistoryEntry {
  payload: IdentifyResponse
  /** what produced this serial: "identified", "re-level to 50", ... */
  label: string
}

export interface PendingTransform {
  result: TransformResponse
  label: string
  /** null while /api/diff is loading; [] when nothing differs */
  diff: DiffRow[] | null
  diffError: string | null
}

export interface WorkbenchState {
  stack: HistoryEntry[]
  pending: PendingTransform | null
}

export type WorkbenchAction =
  | { type: 'loaded'; payload: IdentifyResponse; label?: string }
  | { type: 'proposed'; result: TransformResponse; label: string }
  | { type: 'diffLoaded'; serial: string; rows: DiffRow[] }
  | { type: 'diffFailed'; serial: string; message: string }
  | { type: 'accept' }
  | { type: 'discard' }
  | { type: 'undo' }
  | { type: 'reset' }

export const emptyWorkbench: WorkbenchState = { stack: [], pending: null }

export function currentEntry(state: WorkbenchState): HistoryEntry | null {
  return state.stack[state.stack.length - 1] ?? null
}

export function workbenchReducer(state: WorkbenchState, action: WorkbenchAction): WorkbenchState {
  switch (action.type) {
    case 'loaded':
      return { stack: [{ payload: action.payload, label: action.label ?? 'identified' }], pending: null }
    case 'proposed':
      if (!currentEntry(state)) return state
      return { ...state, pending: { result: action.result, label: action.label, diff: null, diffError: null } }
    case 'diffLoaded':
      if (!state.pending || state.pending.result.serial !== action.serial) return state
      return { ...state, pending: { ...state.pending, diff: action.rows, diffError: null } }
    case 'diffFailed':
      if (!state.pending || state.pending.result.serial !== action.serial) return state
      return { ...state, pending: { ...state.pending, diff: [], diffError: action.message } }
    case 'accept': {
      if (!state.pending) return state
      const r = state.pending.result
      const payload: IdentifyResponse = {
        serial: r.serial,
        info: r.info,
        odds: r.odds,
        parts: r.parts,
        problems: r.problems,
        is_weapon: r.is_weapon,
        can_set_element: r.can_set_element,
      }
      return { stack: [...state.stack, { payload, label: state.pending.label }], pending: null }
    }
    case 'discard':
      return state.pending ? { ...state, pending: null } : state
    case 'undo':
      if (state.stack.length <= 1) return state
      return { stack: state.stack.slice(0, -1), pending: null }
    case 'reset':
      return emptyWorkbench
    default:
      return state
  }
}
