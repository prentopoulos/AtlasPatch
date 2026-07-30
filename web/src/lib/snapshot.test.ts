import { describe, expect, it } from "vitest";
import {
  SNAPSHOT_SCHEMA_VERSION,
  parseSnapshot,
  parseSnapshotText,
} from "./snapshot";
import demoSnapshot from "@/fixtures/demo-snapshot.json";

describe("parseSnapshot", () => {
  it("accepts the bundled demo snapshot", () => {
    const result = parseSnapshot(demoSnapshot);
    expect(result.status).toBe("ok");
    if (result.status === "ok") {
      expect(result.snapshot.schema_version).toBe(SNAPSHOT_SCHEMA_VERSION);
      expect(result.snapshot.runs.length).toBeGreaterThan(0);
    }
  });

  it("reports a version mismatch without inspecting runs", () => {
    const result = parseSnapshot({
      schema_version: SNAPSHOT_SCHEMA_VERSION + 1,
      agents: [],
      runs: "not even an array",
    });
    expect(result).toEqual({
      status: "version-mismatch",
      found: SNAPSHOT_SCHEMA_VERSION + 1,
      expected: SNAPSHOT_SCHEMA_VERSION,
    });
  });

  it("rejects a payload missing schema_version as malformed", () => {
    const result = parseSnapshot({ agents: [], runs: [] });
    expect(result.status).toBe("malformed");
  });

  it("rejects a run with the wrong shape as malformed", () => {
    const result = parseSnapshot({
      schema_version: SNAPSHOT_SCHEMA_VERSION,
      agents: ["planner"],
      runs: [{ job_id: 123 }],
    });
    expect(result.status).toBe("malformed");
  });
});

describe("parseSnapshotText", () => {
  it("treats invalid JSON as malformed, not a thrown error", () => {
    const result = parseSnapshotText("{ not json");
    expect(result.status).toBe("malformed");
  });

  it("round-trips the demo snapshot through text", () => {
    const result = parseSnapshotText(JSON.stringify(demoSnapshot));
    expect(result.status).toBe("ok");
  });
});
