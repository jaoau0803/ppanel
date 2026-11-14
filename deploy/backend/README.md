# 后端 GHCR 版本发布

发布流程位于父仓库 `.github/workflows/release-backend.yml`，不修改后端子模块。复用 `backend/Dockerfile`，构建 `linux/amd64`、`linux/arm64` 镜像，注入上游支持的 `VERSION`、`CHANNEL`、`BUILD_TIME`。

## GitHub 配置

1. 将部署文件提交并推送到父仓库默认分支。
2. 在父仓库 Settings → Environments 创建 `backend-release`，建议添加审批和可信分支/标签限制。该工作流会执行检出的后端代码，只对可信版本授权发布。
3. 若后端子模块私有，在该 Environment 添加 Secret `BACKEND_READ_TOKEN`，使用仅能读取后端仓库的 fine-grained PAT，权限 Contents: Read。公开子模块通常不需要。
4. 发布 GHCR 使用自动生成的 `GITHUB_TOKEN`，工作流已声明 `packages: write`，不需要 Docker Hub 凭据或额外 GHCR PAT。组织策略仍需允许 Actions 创建/写入 Packages。

**不需要配置 Variables。** 默认镜像名是 `ghcr.io/<父仓库owner的小写形式>/ppanel-backend`。若同名包已存在但属于其他仓库，在 Package Settings → Manage Actions access 中授权父仓库写入权限，或先解决命名冲突。

## 手动发布（推荐首次使用）

父仓库 Actions → Release Backend Image → Run workflow：

- Branch：要发布的父仓库分支；后端使用该父仓库提交记录的子模块版本，不自动跟随子模块分支最新提交。
- `version`：例如 `1.2.3`、`1.2.3-beta.1`、`1.2.3-rc.1`，也接受前导 `v`。这是你自己的镜像版本，不会在后端子模块创建标签。
- `publish_latest`：默认 false，只有确认正式发布时才勾选。预发布不能更新 latest。

流程检出指定后端提交、执行 `go test ./...`，通过后构建并推送镜像。没有配置外部数据库 DSN，需数据库的集成测试是否跳过由上游测试决定；不等同于完整生产验收。

## 标签触发

在**父仓库**创建并推送 `backend-v1.2.3` 或 `backend-v1.2.3-beta.1` 标签也会发布。标签必须指向已经更新好后端子模块引用的父仓库提交。

此模式仅发布版本标签，不自动更新 `latest`，避免不同发布线意外覆盖正式默认版本。需要更新 latest 时手动运行并明确勾选。

## 产物与公共可见性

每次发布生成：

```text
ghcr.io/<owner>/ppanel-backend:1.2.3
ghcr.io/<owner>/ppanel-backend:1.2.3-sha-<后端提交前12位>
```

勾选 `publish_latest` 时额外发布 `:latest`。不自动创建 major/minor/lts 浮动标签、不创建 GitHub Release、不推送二进制附件。

**GHCR 新 Package 通常默认 Private，即使源仓库是公开的。首次成功推送后，需要进入 owner 的 Packages → ppanel-backend → Package settings → Change visibility → Public。** Public 通常不能再改回 Private，请确认后端源码及镜像允许公开。源仓库可以保持私有，但镜像的二进制、构建元数据及上下文中包含的文件将对外公开。

Public 设置完成后可以匿名拉取：

```sh
docker pull ghcr.io/<owner>/ppanel-backend:1.2.3
```

工作流摘要提供精确 digest。生产环境优先使用 `ghcr.io/<owner>/ppanel-backend@sha256:...` 固定镜像；版本标签与提交后缀标签技术上仍可被重复发布覆盖，不应把它们视为不可变。请避免重复使用版本号。

## 运行和回滚注意事项

本工作流只发布镜像，不部署服务器，也不连接数据库或执行迁移。运行参数参考 `backend/docker-compose.yml` 及后端文档。

当前上游镜像使用 UID/GID `65532:65532`，配置及可写卷需正确授权；不要把真实配置、JWT secret 或数据库凭据放入构建上下文。工作流复用上游 `.dockerignore`，发布前应检查它仍能排除敏感文件。

后端启动可能自动执行数据库迁移。回滚旧镜像不等同于回滚数据库，升级前备份，确认迁移兼容性后再操作。

Go 版本及构建基础镜像沿用 `backend/go.mod`、`backend/Dockerfile`；若上游声明的工具链或镜像版本不可下载，CI 会失败，不会通过父仓库静默降级工具链。

## 本地验证

无需第三方 Python 包：

```sh
python3 -m unittest discover -s deploy/backend -p 'test_*.py'
```

完整镜像构建需要 Docker/Buildx、网络，以及上游要求的 Go 工具链。首次发布之后请核对镜像两种架构、应用版本输出，并实际验证匿名拉取。
