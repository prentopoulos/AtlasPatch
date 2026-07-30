/**
 * The TypeScript mirror of the frozen `gui-snapshot` payload (phase-8 contract) and the
 * loader that turns an untrusted file into a typed, version-checked snapshot.
 *
 * `SNAPSHOT_SCHEMA_VERSION` is pinned to the producer's `atlas_conductor.gui.snapshot`
 * constant (design D-REACT-2): the loader compares a file's `schema_version` to it and
 * surfaces an explicit incompatibility state on mismatch rather than mis-rendering an
 * unrecognized shape. A malformed file yields an error result, never a thrown exception.
 */

/** Pinned to `atlas_conductor.gui.snapshot.SNAPSHOT_SCHEMA_VERSION`. Bump only in lockstep. */
export const SNAPSHOT_SCHEMA_VERSION = 1;

/** The four terminal structural outcomes, in report order (mirrors `model.TERMINAL_OUTCOMES`). */
export const TERMINAL_OUTCOMES = ["valid", "skipped", "quarantined", "blocked"] as const;
export type Verdict = (typeof TERMINAL_OUTCOMES)[number];

export interface TraceEvent {
  agent: string;
  event: string;
  slide_stem?: string;
  stage?: string;
  reason_code?: string;
  detail?: string;
  timestamp?: string;
  [key: string]: unknown;
}

export interface SlideView {
  slide_stem: string;
  outcome: string;
  reason_code: string;
  detail: string;
  trace: TraceEvent[];
}

export interface ChoreographyState {
  active: string | null;
  lit: Record<string, boolean>;
  slide_stem: string | null;
  stage: string | null;
  now_processing: string | null;
}

export interface Edge {
  from_agent: string;
  to_agent: string;
  count: number;
  last_timestamp: string;
}

export interface MessageFlowState {
  edges: Edge[];
  latest: [string, string] | null;
  has_flow: boolean;
}

export interface RunView {
  job_id: string;
  job: Record<string, unknown>;
  cohort_size: number;
  counts: Record<Verdict, number>;
  slides: SlideView[];
  choreography: ChoreographyState;
  message_flow: MessageFlowState;
}

export interface Snapshot {
  schema_version: number;
  agents: string[];
  runs: RunView[];
}

/** The outcome of loading an untrusted snapshot: exactly one of three explicit states. */
export type LoadResult =
  | { status: "ok"; snapshot: Snapshot }
  | { status: "version-mismatch"; found: unknown; expected: number }
  | { status: "malformed"; message: string };

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function malformed(message: string): LoadResult {
  return { status: "malformed", message };
}

/** Validate one run's shape enough to render it without a runtime crash. */
function isValidRun(run: unknown): run is RunView {
  if (!isObject(run)) return false;
  if (typeof run.job_id !== "string") return false;
  if (!isObject(run.counts)) return false;
  if (!Array.isArray(run.slides)) return false;
  if (!isObject(run.choreography) || !isObject(run.message_flow)) return false;
  return true;
}

/**
 * Turn a parsed JSON value into a typed snapshot, a version-mismatch, or a malformed result.
 *
 * Order matters (spec): a value with a numeric `schema_version` that differs from the pinned
 * version is reported as an incompatibility (we do not inspect its runs — the shape may have
 * changed); only a version-matching payload is validated structurally.
 */
export function parseSnapshot(raw: unknown): LoadResult {
  if (!isObject(raw)) return malformed("Snapshot must be a JSON object.");

  const version = raw.schema_version;
  if (typeof version !== "number") {
    return malformed("Snapshot is missing a numeric `schema_version`.");
  }
  if (version !== SNAPSHOT_SCHEMA_VERSION) {
    return { status: "version-mismatch", found: version, expected: SNAPSHOT_SCHEMA_VERSION };
  }

  if (!Array.isArray(raw.agents) || !raw.agents.every((a) => typeof a === "string")) {
    return malformed("Snapshot `agents` must be an array of strings.");
  }
  if (!Array.isArray(raw.runs)) {
    return malformed("Snapshot `runs` must be an array.");
  }
  if (!raw.runs.every(isValidRun)) {
    return malformed("One or more runs have an unexpected shape.");
  }

  return { status: "ok", snapshot: raw as unknown as Snapshot };
}

/** Parse raw file text (JSON) into a load result; a JSON syntax error is a malformed result. */
export function parseSnapshotText(text: string): LoadResult {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return malformed("File is not valid JSON.");
  }
  return parseSnapshot(parsed);
}
