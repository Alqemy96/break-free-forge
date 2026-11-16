/**
 * The web contract (docs/WEB_API.md) as TypeScript. One source of truth for every payload the UI
 * reads or sends. Field names stay snake_case exactly as the server writes them.
 */

// ---- shared vocabulary (core/vocab.py) ----------------------------------------------------------

export const ELEMENT_IDS = ['cryo', 'fire', 'radiation', 'shock', 'corrosive', 'impact'] as const
export type ElementId = (typeof ELEMENT_IDS)[number]

export const RARITIES = ['Common', 'Uncommon', 'Rare', 'Epic', 'Legendary', 'Pearl', 'Vile'] as const
export type Rarity = (typeof RARITIES)[number]

export const MODULE_STATES = ['ok', 'degraded', 'failed', 'blocked'] as const
export type ModuleState = (typeof MODULE_STATES)[number]

export const ERROR_CODES = [
  'bad_request',
  'serial_error',
  'module_unavailable',
  'data_missing',
  'not_found',
  'internal',
] as const
export type ErrorCode = (typeof ERROR_CODES)[number]

/** JSON as it arrives (diff rows carry arbitrary JSON values). */
export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue }

// ---- errors ----------------------------------------------------------------------------------------

export interface ErrorBody {
  /** `module` is set on 503 module_unavailable when the server can name the sick module */
  error: { code: ErrorCode; message: string; module?: string }
}

// ---- GET /api/meta ---------------------------------------------------------------------------------

export interface ElementOption {
  id: ElementId
  label: string
}

export type TypeGroup = 'weapon' | 'gear'

export interface TypeOption {
  id: string
  label: string
  group: TypeGroup
}

export interface Meta {
  version: string
  level: number
  character: string
  owned_packs: string[]
  /** null when the catalog module is unavailable (meta never 503s) */
  catalog_count: number | null
  /** null when the data module is unavailable */
  manifest_version: string | null
  elements: ElementOption[]
  rarities: string[]
  characters: string[]
  types: TypeOption[]
}

// ---- GET /api/health (rows from core.doctor.diagnose) ----------------------------------------------

export interface HealthCheck {
  name: string
  ok: boolean
  detail: string
}

export interface ModuleRow {
  name: string
  state: ModuleState
  detail: string
  purpose: string
  requires: string[]
  contract_problems: string[]
  checks: HealthCheck[]
}

export interface Health {
  ok: boolean
  modules: ModuleRow[]
}

// ---- GET /api/stats (catalog.stats() verbatim) -----------------------------------------------------

export type Stats = Record<string, Record<string, number>>

// ---- GET /api/search -------------------------------------------------------------------------------

export interface SearchParams {
  query?: string
  type?: string
  element?: ElementId
  manufacturer?: string
  rarity?: string
  character?: string
  /** 1..200, server default 25 */
  limit?: number
  include_unowned?: boolean
  verify_element?: boolean
  /** present: every returned serial is re-leveled */
  level?: number
}

/** `ops.describe` of the (re-leveled) serial: the bitstream is the truth. */
export interface Decoded {
  display_name: string | null
  category: string | null
  rarity: string | null
  element: ElementId | null
  /** null when the serial could not be decoded (see warnings) */
  owned: boolean | null
  warnings: string[]
}

export interface SearchResultRow {
  serial: string
  name: string
  type: string
  weapon_type: string
  manufacturer: string
  label: string
  /** catalog hint */
  rarity: string
  /** catalog hint */
  element: ElementId | null
  source: string
  level: number | null
  decoded: Decoded
  /** not in the contract; tolerated if the server adds re-level warnings like the cli does */
  warnings?: string[]
}

export interface HiddenPack {
  pack: string
  label: string
  count: number
}

export interface SearchResponse {
  count: number
  level: number | null
  results: SearchResultRow[]
  hidden: HiddenPack[]
  dropped_element_mismatch: number
  /** server notices, e.g. the config character applied to a class-mod search */
  notes?: string[]
}

// ---- POST /api/identify ----------------------------------------------------------------------------

export interface PartRef {
  token_index: number
  category_id: number | null
  index: number
  raw: string | null
  name: string | null
  category_link: number | null
}

/** core.types.ItemInfo.to_dict(): tuples arrive as arrays. */
export interface ItemInfo {
  serial: string
  category_id: number | null
  category: string | null
  level: number | null
  rarity: string | null
  element: ElementId | null
  legendary_name: string | null
  display_name: string | null
  parts: PartRef[]
  /** (rarity, name) pairs of lower-tier composition parts */
  other_components: [string, string | null][]
  tokens: string
  content_pack: string
  content_pack_label: string
  owned: boolean
  manifest_ok: boolean
  warnings: string[]
}

export interface IdentifyPart {
  /** index into ops.part_list: what swap positions mean */
  position: number
  token_index: number
  label: string
  category_id: number | null
  index: number
  raw: string | null
  category_link: number | null
}

export interface IdentifyRequest {
  serial: string
  level?: number
}

export interface IdentifyResponse {
  serial: string
  info: ItemInfo
  odds: string
  parts: IdentifyPart[]
  problems: string[]
  is_weapon: boolean
  can_set_element: boolean
}

// ---- POST /api/transform ---------------------------------------------------------------------------

export type TransformRequest =
  | { serial: string; op: 'relevel'; level: number }
  | { serial: string; op: 'set_element'; element: ElementId }
  | { serial: string; op: 'reseed'; seed?: number }
  | { serial: string; op: 'swap'; source: string; positions: number[]; allow_cross: boolean }

export type TransformOp = TransformRequest['op']

export interface TransformResponse extends IdentifyResponse {
  previous: string
  note: string
  /** reseed only: the seed that was used (random when none was sent) */
  seed?: number
}

// ---- POST /api/diff --------------------------------------------------------------------------------

export interface DiffRow {
  field: string
  a: JsonValue
  b: JsonValue
}

export interface DiffResponse {
  rows: DiffRow[]
}

// ---- POST /api/build -------------------------------------------------------------------------------

/** core.types.LoadoutRequest. Either `serial` (explicit) or search fields (auto-pick). */
export interface LoadoutRequest {
  group?: string | null
  serial?: string | null
  query?: string | null
  type?: string | null
  element?: string | null
  manufacturer?: string | null
  rarity?: string | null
  character?: string | null
  count?: number
  note?: string
  display_name?: string | null
  /** explicit entries: manufacturer/type label to show (LoadoutRequest field; see CHANGE_REQUESTS) */
  label?: string
  /** explicit entries: item name hint (LoadoutRequest field; see CHANGE_REQUESTS) */
  name?: string
}

export interface BuildRequest {
  requests: LoadoutRequest[]
  /** omitted: do not re-level */
  level?: number
  title?: string
}

export interface LoadoutItem {
  name: string
  serial: string
  level: number | null
  group: string | null
  display_name: string | null
  manufacturer: string
  label: string
  type: string
  weapon_type: string
  rarity: string
  element: ElementId | null
  category: string | null
  legendary_name: string | null
  parts: string[]
  odds: string
  source: string
  note: string
  warnings: string[]
  shown_name: string
}

export interface Loadout {
  title: string
  level: number | null
  groups: string[]
  unmatched: string[]
  warnings: string[]
  items: LoadoutItem[]
}

export interface BuildResponse {
  loadout: Loadout
  html: string
  text: string
}

// ---- the client surface (real server or mock) ------------------------------------------------------

export interface RequestOptions {
  signal?: AbortSignal
}

export interface Api {
  meta(opts?: RequestOptions): Promise<Meta>
  health(opts?: RequestOptions): Promise<Health>
  stats(opts?: RequestOptions): Promise<Stats>
  search(params: SearchParams, opts?: RequestOptions): Promise<SearchResponse>
  identify(body: IdentifyRequest, opts?: RequestOptions): Promise<IdentifyResponse>
  transform(body: TransformRequest, opts?: RequestOptions): Promise<TransformResponse>
  diff(a: string, b: string, opts?: RequestOptions): Promise<DiffResponse>
  build(body: BuildRequest, opts?: RequestOptions): Promise<BuildResponse>
}
