# Cloudflare Pages 部署

部署层位于父仓库，不修改 `frontend` 子模块、上游构建脚本或发布流程。用户端和管理端各使用一个 Pages 项目；静态资源由 Pages 提供，`/v1/*` 复用 `frontend/functions` 代理后端。

## 1. 创建资源

**无需手动创建 Pages 项目或提前上传编译产物。** Actions 构建成功后会查询项目，不存在时通过 `wrangler pages project create` 自动创建 Direct Upload 项目，再上传静态资源及 Functions。

默认名称为用户端 `ppanel-user`、管理端 `ppanel-admin`；可通过 `CF_USER_PROJECT` / `CF_ADMIN_PROJECT` 覆盖。项目名和 `pages.dev` 子域可能存在可用性限制，若默认名称不可用，请配置自己的唯一名称。项目创建后可在 Cloudflare 控制台绑定自定义域名，不要再为同一项目开启另一套 Git 自动部署。

新项目的生产分支使用 `CF_PRODUCTION_BRANCH`（默认 `main`）。已有项目会检查生产分支是否匹配，不匹配则报错，不修改或覆盖项目设置。Wrangler 根据分支判断生产/预览。首次运行 Preview 也会创建项目，但仅上传 Preview 部署；生产站点需运行 Production 部署后才有内容。

后端必须是 Cloudflare 能访问的 HTTPS 服务，不能指回前端域名。它仍需自行做认证、管理权限校验和限流。API 路径保持 `/v1/...`，`API_BASE_URL` 只能填写 origin，不包含 `/v1`。

## 2. 本地准备

要求 Node.js 22 LTS、Bun 1.3.1。Wrangler 在此目录单独锁定，不加入前端依赖。

从父仓库根目录执行：

```sh
git submodule update --init frontend
bun install --cwd deploy/cloudflare --frozen-lockfile --ignore-scripts
HUSKY=0 bun install --cwd frontend --frozen-lockfile --ignore-scripts
bun test deploy/cloudflare
bun test frontend/tests/functions
```

子模块安装依赖使用现有锁文件；如果其中的镜像地址不可用，需要先恢复网络或镜像服务，不要为了部署随意重写上游锁文件。

## 3. 手动验证与部署

从 `deploy/cloudflare` 目录执行。以下域名和项目名仅为示例，需要替换为自己的值：

```sh
API_BASE_URL=https://api.example.com \
SITE_ORIGIN=https://panel.example.com \
CF_PAGES_PROJECT=ppanel-user \
bun run deploy.ts user production --dry-run
```

`--dry-run` 实际构建目标应用并编译 Functions，但不查询或创建云端项目，也不上传，不需要 Cloudflare 凭据。应用构建包含上游的 TypeScript 检查。

部署前通过安全的 shell 环境或密码管理器设置 `CLOUDFLARE_API_TOKEN`、`CLOUDFLARE_ACCOUNT_ID`，不要写入配置或提交仓库。API Token 使用限定账户的 **Cloudflare Pages: Edit** 权限。

```sh
API_BASE_URL=https://api.example.com \
SITE_ORIGIN=https://panel.example.com \
CF_PAGES_PROJECT=ppanel-user \
bun run deploy.ts user production
```

管理端将目标改为 `admin`，并更换项目和域名。预览部署示例：

```sh
API_BASE_URL=https://staging-api.example.com \
SITE_ORIGIN=https://panel.example.com \
CF_PAGES_PROJECT=ppanel-user \
CF_PREVIEW_BRANCH=preview-test \
bun run deploy.ts user preview
```

### 参数和变量

| 名称 | 说明 |
| --- | --- |
| 第一个参数 | `user` 或 `admin` |
| 第二个参数 | `production` 或 `preview` |
| `API_BASE_URL` | 必填，后端 HTTPS origin；构建暂存配置中的运行时变量 |
| `CF_PAGES_PROJECT` | 可选，默认 `ppanel-user` 或 `ppanel-admin`；不存在时自动创建 |
| `SITE_ORIGIN` | 建议设置，用于检测明显的代理循环；不能识别所有域名别名循环 |
| `CF_PRODUCTION_BRANCH` | 默认 `main`，必须匹配 Pages 项目设置 |
| `CF_PREVIEW_BRANCH` | Preview 必填，且不能与生产分支相同 |
| `CLOUDFLARE_ACCOUNT_ID` | 实际上传时必填 |
| `CLOUDFLARE_API_TOKEN` | 实际上传时必填，禁止提交 |

配置文件是模板，脚本会在临时目录补充项目名及生产/预览的运行时 `API_BASE_URL`。后端地址不是浏览器密钥；这里不将任何凭据注入前端。

每次调用只上传一次目标环境，生成的生产/预览变量相同是为了适配 Wrangler 的环境选择；**不会同时部署两个环境**。更换后端地址需重新部署。脚本管理的 `API_BASE_URL` 不应再通过 Dashboard 维护另一份来源。

## 4. GitHub Actions

工作流位于父仓库 `.github/workflows/deploy-cloudflare.yml`，仅支持手动触发，可选择单端或两端，默认 Preview。

创建两个 GitHub Environments：

- `cloudflare-production`：建议配置 required reviewers，并限定可信分支。
- `cloudflare-preview`：使用测试后端，不要连接生产数据库。

分别配置以下 Environment variables：

| Variable | 例子 |
| --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare 账户 ID |
| `CF_USER_PROJECT` | 可选，默认 `ppanel-user`；建议改为带个人/组织前缀的名称 |
| `CF_ADMIN_PROJECT` | 可选，默认 `ppanel-admin`；建议改为带个人/组织前缀的名称 |
| `CF_USER_ORIGIN` | `https://panel.example.com` |
| `CF_ADMIN_ORIGIN` | `https://admin.example.com` |
| `API_BASE_URL` | 当前环境后端，例如 `https://staging-api.example.com` |
| `CF_PRODUCTION_BRANCH` | `main`，可省略 |

分别配置 Environment secret `CLOUDFLARE_API_TOKEN`。

如果前端子模块为私有仓库，另外配置 secret `FRONTEND_READ_TOKEN`（细粒度 token，仅授予该前端仓库 Contents: Read）。默认 `github.token` 通常只能访问当前仓库。工作流把子模块 SSH 地址临时转换为 HTTPS，不修改 `.gitmodules`，并检出父仓库记录的准确提交。

工作流使用 Bun 1.3.1 和 Node.js 22。两个应用独立部署，不保证原子发布；某端失败时可单独重试。不要在不可信分支运行具有生产 secret 的工作流；本工作流不响应 PR 事件。

## 5. 部署行为与兼容边界

- 在临时目录复制目标 `dist` 和现有 `functions/`，先编译验证，再通过 Pages CLI 打包上传，结束后清理临时目录。
- 构建强制跳过 Turbo 缓存命中，确保同源 API 配置没有复用旧缓存。
- 清空构建环境里的 `VITE_API_BASE_URL`、`VITE_API_PREFIX`；应用 `.env*` 若包含非空 API 配置则拒绝部署。
- 产物 `_routes.json` 仅让 `/v1`、`/v1/*` 进入 Functions，静态文件不调用 Functions。
- 产物 `_headers` 为入口 HTML、回调、版本与 `/assets/*` 设置重新验证缓存，带哈希的 `/static/*` 长缓存。API 响应不受静态 `_headers` 控制，不能配置全站 Cache Everything。
- 保留上游 `_redirects` 和真实的 OAuth/bind 回调文件，不额外强制全站重写。当前应用使用 Hash Router。
- 现有代理保留后端 OAuth 302、转发可信客户端 IP，且删除 `Set-Cookie`。未来若认证依赖 Cookie，必须重新适配，不能视为通用 Cookie 代理。
- 新版本上游若改变 API 前缀、构建目录、路由或 `functions` 结构，应重新验收，不承诺任意上游变更自动兼容。
- `VITE_*` 是公开构建变量。不要配置 `VITE_USER_EMAIL`、`VITE_USER_PASSWORD` 等真实账号信息。

本方案仅部署前端及边缘代理，不部署后端、数据库或节点。Pages Functions 有请求额度与套餐限制，API 流量也计入 Functions 使用量。

## 6. 验收与回滚

部署后逐项验证：

1. 两端首页、JS/CSS、翻译、图标和 `version.lock` 可访问。
2. `/v1/...` 返回 API 响应而非 HTML，未授权请求仍被后端拒绝。
3. 登录、带 Authorization 的请求、POST 和上传正常。
4. OAuth 平台及后端配置使用正确域名；`/oauth/<provider>/`、`/bind/<provider>/` 加载真实回调页面，Apple POST 回调的 302 到达浏览器。
5. 后端日志中的客户端 IP 正确，用户接口不被共享缓存。
6. Preview 确实连接测试后端，而不是生产后端。

在 Cloudflare Pages 的 Deployments 页面选择该应用之前的成功生产部署回滚；两端分别操作。也可以检出父仓库历史提交，恢复其记录的子模块版本再手动部署。部署产物不提交 Git，密钥不存入源代码。
