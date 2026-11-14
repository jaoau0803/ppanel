import { describe, expect, test } from "bun:test";
import { ensureProject, projectName, parseArgs, validateBackend } from "./deploy";

describe("deployment validation", () => {
  test("uses independent defaults and accepts overrides", () => {
    expect(projectName("user")).toBe("ppanel-user");
    expect(projectName("admin")).toBe("ppanel-admin");
    expect(projectName("user", "my-panel")).toBe("my-panel");
    expect(() => projectName("user", "Bad/name")).toThrow();
  });
  test("creates only missing projects", async () => {
    let created = 0;
    const create = async () => { created++; };
    const mock = (status: number, body: unknown) => (async () => Response.json(body, { status })) as unknown as typeof fetch;
    await ensureProject("account", "token", "panel", "main", create, mock(404, { success: false }));
    expect(created).toBe(1);
    await ensureProject("account", "token", "panel", "main", create, mock(200, { success: true, result: { production_branch: "main" } }));
    expect(created).toBe(1);
    for (const status of [401, 403, 500]) {
      await expect(ensureProject("account", "token", "panel", "main", create, mock(status, { success: false }))).rejects.toThrow();
    }
    await expect(ensureProject("account", "token", "panel", "main", create, mock(200, { success: true, result: { production_branch: "other" } }))).rejects.toThrow();
    expect(created).toBe(1);
  });
  test("accepts an HTTPS backend origin", () => {
    expect(validateBackend("https://api.example.com/")).toBe("https://api.example.com");
  });
  test("explains missing and malformed backend configuration", () => {
    expect(() => validateBackend("")).toThrow("API_BASE_URL is required");
    expect(() => validateBackend("   ")).toThrow("API_BASE_URL is required");
    expect(() => validateBackend("not-a-url")).toThrow("API_BASE_URL must be a valid HTTPS origin");
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
