import { describe, expect, test } from "bun:test";
import { parseArgs, validateBackend } from "./deploy";

describe("deployment validation", () => {
  test("accepts an HTTPS backend origin", () => {
    expect(validateBackend("https://api.example.com/")).toBe("https://api.example.com");
  });
  test("rejects unsafe or ambiguous backends", () => {
    for (const value of ["", "http://api.example.com", "https://api.example.com/v1", "https://user:pass@api.example.com", "https://api.example.com/?x=1", "https://api.example.com/#hash"]) {
      expect(() => validateBackend(value)).toThrow();
    }
    expect(() => validateBackend("https://panel.example.com", "https://panel.example.com/")).toThrow();
  });
  test("accepts only supported targets and environments", () => {
    expect(parseArgs(["user", "preview", "--dry-run"])).toEqual({ app: "user", environment: "preview", dryRun: true });
    for (const args of [[], ["other", "production"], ["admin", "prod"], ["user", "production", "--unknown"]]) expect(() => parseArgs(args)).toThrow();
  });
});
