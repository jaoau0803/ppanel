import { cp, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");
export const apps = { user: "ppanel-user-web", admin: "ppanel-admin-web" } as const;

export function projectName(app: keyof typeof apps, override?: string): string {
  const name = override || `ppanel-${app}`;
  if (!/^[a-z0-9][a-z0-9-]{0,57}[a-z0-9]$/.test(name)) throw new Error("Pages project name must be 2–59 lowercase letters, digits or hyphens, with no leading/trailing hyphen");
  return name;
}

export async function ensureProject(
  account: string,
  token: string,
  project: string,
  productionBranch: string,
  create: () => Promise<void>,
  request: typeof fetch = fetch,
) {
  const response = await request(`https://api.cloudflare.com/client/v4/accounts/${encodeURIComponent(account)}/pages/projects/${encodeURIComponent(project)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = await response.json() as { success?: boolean; result?: { production_branch?: string }; errors?: { code: number; message: string }[] };
  if (response.ok && body.success) {
    if (body.result?.production_branch !== productionBranch) throw new Error(`Existing Pages project ${project} has a different production branch; set CF_PRODUCTION_BRANCH to match it`);
    console.log(`Using existing Pages project: ${project}`);
    return;
  }
  // Cloudflare uses code 8000007 for a missing Pages project. Never create on auth/network errors.
  if (response.status === 404 || body.errors?.some((error) => error.code === 8000007)) {
    console.log(`Creating Pages project: ${project}`);
    await create();
    return;
  }
  throw new Error(`Unable to inspect Pages project (${response.status}): ${body.errors?.map((error) => error.message).join("; ") || "Cloudflare API error"}`);
}

export function validateBackend(value: string, targetOrigin?: string): string {
  const url = new URL(value);
  if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash || url.pathname !== "/") {
    throw new Error("API_BASE_URL must be an HTTPS origin without credentials, path, query or fragment");
  }
  if (targetOrigin && url.origin === new URL(targetOrigin).origin) {
    throw new Error("API_BASE_URL must not point to the Pages site");
  }
  return url.origin;
}

export function parseArgs(args: string[]): { app: keyof typeof apps; environment: "production" | "preview"; dryRun: boolean } {
  const [app, environment, ...extra] = args;
  if (!(app === "user" || app === "admin") || !(environment === "production" || environment === "preview") || extra.some((arg) => arg !== "--dry-run") || extra.length > 1) {
    throw new Error("Usage: bun run deploy.ts <user|admin> <production|preview> [--dry-run]");
  }
  return { app, environment, dryRun: extra.includes("--dry-run") };
}

async function run(command: string[], cwd: string, env: Record<string, string | undefined> = {}) {
  const child = Bun.spawn(command, { cwd, env: { ...process.env, ...env }, stdout: "inherit", stderr: "inherit", stdin: "ignore" });
  if (await child.exited !== 0) throw new Error(`Command failed: ${command.join(" ")}`);
}

async function main() {
  const { app, environment, dryRun } = parseArgs(process.argv.slice(2));
  const backend = validateBackend(process.env.API_BASE_URL || "", process.env.SITE_ORIGIN);
  const project = projectName(app, process.env.CF_PAGES_PROJECT);
  const productionBranch = process.env.CF_PRODUCTION_BRANCH || "main";
  const branch = environment === "production" ? productionBranch : process.env.CF_PREVIEW_BRANCH;
  if (!branch || (environment === "preview" && branch === productionBranch)) throw new Error("Preview requires CF_PREVIEW_BRANCH distinct from CF_PRODUCTION_BRANCH");
  if (!dryRun && (!process.env.CLOUDFLARE_ACCOUNT_ID || !process.env.CLOUDFLARE_API_TOKEN)) throw new Error("CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required");

  const frontend = join(root, "frontend");
  const temp = await mkdtemp(join(tmpdir(), "ppanel-pages-"));
  try {
    // Empty values override inherited Vite settings; .env files are checked too.
    const appDir = join(frontend, "apps", app);
    for (const file of [".env", ".env.local", ".env.production", ".env.production.local"]) {
      const text = await readFile(join(appDir, file), "utf8").catch((error) => {
        if ((error as NodeJS.ErrnoException).code === "ENOENT") return "";
        throw error;
      });
      if (/^\s*(?:export\s+)?VITE_API_(?:BASE_URL|PREFIX)\s*=\s*["']?[^\s"'#]/m.test(text)) {
        throw new Error(`Remove VITE_API_BASE_URL/VITE_API_PREFIX from ${appDir}/${file} for same-origin deployment`);
      }
    }
    await run(["bun", "run", "build", `--filter=${apps[app]}`, "--force"], frontend, { VITE_API_BASE_URL: "", VITE_API_PREFIX: "", HUSKY: "0", CI: "true" });
    await cp(join(appDir, "dist"), join(temp, "dist"), { recursive: true });
    await cp(join(frontend, "functions"), join(temp, "functions"), { recursive: true });
    await writeFile(join(temp, "dist", "_routes.json"), JSON.stringify({ version: 1, include: ["/v1", "/v1/*"], exclude: [] }));
    await writeFile(join(temp, "dist", "_headers"), `/\n  Cache-Control: no-cache\n/index.html\n  Cache-Control: no-cache\n/version.lock\n  Cache-Control: no-cache\n/assets/*\n  Cache-Control: no-cache\n/oauth/*\n  Cache-Control: no-cache\n/bind/*\n  Cache-Control: no-cache\n/static/*\n  Cache-Control: public, max-age=31536000, immutable\n`);
    const template = JSON.parse(await readFile(join(here, `${app}.wrangler.json`), "utf8"));
    await writeFile(join(temp, "wrangler.json"), JSON.stringify({ ...template, name: project, vars: { API_BASE_URL: backend }, env: { preview: { vars: { API_BASE_URL: backend } } } }, null, 2));
    const wrangler = join(here, "node_modules", ".bin", "wrangler");
    // Build from the staging root so Wrangler discovers functions/, not just dist/.
    const wranglerEnv = { WRANGLER_LOG_PATH: join(temp, "wrangler.log"), WRANGLER_SEND_METRICS: "false" };
    await run([wrangler, "pages", "functions", "build", "functions", "--outdir=.functions-build"], temp, wranglerEnv);
    if (dryRun) {
      console.log(`Validated ${app}/${environment}: static assets and Functions compiled; nothing uploaded.`);
      return;
    }
    await ensureProject(process.env.CLOUDFLARE_ACCOUNT_ID!, process.env.CLOUDFLARE_API_TOKEN!, project, productionBranch,
      () => run([wrangler, "pages", "project", "create", project, `--production-branch=${productionBranch}`], temp, wranglerEnv));
    await run([wrangler, "pages", "deploy", "dist", `--project-name=${project}`, `--branch=${branch}`, "--commit-dirty=true"], temp, wranglerEnv);
  } finally {
    await rm(temp, { recursive: true, force: true });
  }
}

if (import.meta.main) main().catch((error) => { console.error(error.message); process.exitCode = 1; });
