# 公司 ACK 部署说明

2026-11-16：已按公司的示例补齐本项目 GitLab CI、Helm Chart 和部署前检查。尚未创建公司项目、构建 Linux 镜像或连接 ACK；没有生成正式网站地址。公司集群、域名、权限和备份由 IT 分配后才能上线。

## 你现在做什么

把这份源码包发给 IT，并发送下面的话：

> VIP 报销网站已按你提供的 simple-python-app 示例补齐独立项目的 GitLab CI 和 Helm 配置，详见 ACK_DEPLOY.md。约 30 位嘉宾使用，需在微信中无需飞连/VPN访问 HTTPS 地址。请帮我创建公司 GitLab 私有项目，分配专用 Namespace、现有 ACK context、公网域名及 IngressClass，并配置下表的 CI 变量、应用 Secret、镜像拉取 Secret 和独立 PVC。请确认 general-runner 可以构建 linux/amd64 镜像，并安排数据备份与恢复验证。代码是干净源码，首次部署使用空数据库。

收到项目网址、部署空间和域名后，继续上传本包代码并执行流水线。不要覆盖 `examples/devops` 或把真实报销资料放进示例 Namespace。无需购买新 ECS。

## IT 配置入口和变量

在新项目 `Settings → CI/CD → Variables` 配置变量。发布任务固定使用 `staging` 环境，与公司的示例一致；请保护默认分支，并按公司流程限制手动发布人员。发布变量应 Protected 且 Environment scope 为 `staging`，不要粘贴到聊天或提交到 Git。

| 名称 | 类型/内容 |
| --- | --- |
| `ACK_KUBE_CONFIG_BASE64` | **File**；文件内容是 Base64 编码的 kubeconfig 文本，与公司示例约定相同。不是原始 kubeconfig，也不是普通变量中的路径。部署身份限制在分配的空间。 |
| `DEPLOY_ACK_NAME` | 分配的 kubeconfig context 名称；示例里的名称不能当成已获授权。 |
| `DEPLOY_NAMESPACE` | 专用于本项目的部署空间；脚本拒绝 `examples`。 |
| `PUBLIC_HOST` | 正式公网域名，不带 `https://` 或路径。 |
| `INGRESS_CLASS` | IT 确认的 IngressClass；需确认公网可达性。 |
| `DATA_PVC_NAME` | IT 预先创建的独立 PVC 名称。 |
| `APP_SECRET_NAME` | 同一空间内的应用 Secret 名称。 |
| `IMAGE_PULL_SECRET_NAME` | 同一空间的镜像拉取 Secret；示例名称仅供 IT 核对。 |
| `TLS_MODE` | `secret` 或 `gateway`，默认 `secret`。 |
| `TLS_SECRET_NAME` | `secret` 模式必填，提供有效证书及密钥的 TLS Secret 名称。 |
| `GATEWAY_HTTPS_CONFIRMED` | `gateway` 模式需 IT 确认证书和 HTTPS 路由后设置为 `1`。 |
| `PUBLIC_ACCESS_CONFIRMED` | IT 确认公网、HTTPS、Host/路径、上传和超时后设置为 `1`。 |
| `TRUST_PROXY_HEADERS` | 默认 `0`。仅当网关覆盖 `X-Real-IP`，且后端访问受限时设为 `1`。 |
| `PROXY_HEADER_CONFIRMED` | 开启代理信任时，IT 确认上述条件后设为 `1`。 |
| `DEPLOY_NAME` | 默认 `vip-reimbursement`；按公司命名规范可修改。 |
| `HELM_TIMEOUT` | 默认 `10m`。 |

`CI_REGISTRY_IMAGE`、`CI_REGISTRY_USER`、`CI_REGISTRY_PASSWORD` 使用 GitLab 内置变量。需启用项目 Container Registry，Runner 可访问公司镜像仓库、Python/系统依赖源和 OCR 官方模型源，并具备 Docker daemon。CI 不自行启动 Docker-in-Docker，与公司示例约定一致。

应用 Secret 包含以下**键名**，值由 IT 在公司认可的私密入口设置：

- `ADMIN_PASSWORD`：独立的后台密码，至少 12 位。
- `GUEST_INVITE_CODE`：固定嘉宾邀请码，至少 6 位；会务确认后通知嘉宾。

真实密码不放 values、源码或 CI 命令行。变更 Secret 后应在维护窗口重启单实例，让新配置生效；本 Chart 不自动轮询 Secret 变化。

## 存储、资源和网络

- 创建 PVC 时不要将其设为 Helm 管理的资源。先规划约 50Gi，使用公司认可的 StorageClass/快照方案；容量按附件规模调整。所有原票据、截图、SQLite、草稿、会话和配置位于 `/data`。
- 容器以 UID/GID `10001` 运行。卷应允许该用户创建文件和将已有配置设为 `0600`；尤其需实测 NAS 的属主和权限。Chart 的 `fsGroup=10001` 不能保证所有存储驱动自动修复属主。初始化阶段会检查可写性。
- Chart 不创建或删除 PVC、应用 Secret、镜像拉取 Secret、TLS Secret，不创建 Namespace。初次 `--atomic` 失败不会删除这些预先分配的资源。平台回收策略仍需 IT 确认。
- 当前 SQLite 版本强制单副本、`Recreate`；不接 HPA。更新会中断服务，应在低峰维护并提示正在上传的用户重试。
- 镜像构建为 Linux amd64，调度到对应节点。初始资源请求 1 CPU / 2Gi，限制 2 CPU / 4Gi；这只是初始配置，需按 OCR 实测调整，不是容量保证。
- OCR 模型在构建时准备；初始化容器把镜像中的模型复制进可写临时卷，避免空卷遮住模型。随后运行一次虚构图片推理检查，成功后才启动网站。`/healthz` 本身仍只检查进程和数据库。
- `8765` 只在集群内服务，Service 为 ClusterIP:80，外部统一走公司 HTTPS 网关。ACK 不运行 Compose 中的 Caddy。
- 网关须保留原 Host 和 `/api/...`、`/admin`、`/assets/...` 等完整路径，转发请求体长度；不能套示例中的 `rewrite-target: /$2`。不支持 chunked 透传给当前标准库后端，网关需正常缓冲请求体并发送 Content-Length。
- 网关允许至少 40MiB 请求（应用单文件上限 35MiB），OCR 请求超时初始至少 180 秒；下载导出需按附件大小实测。HTTP 应重定向到 HTTPS。相关注解由 IT 根据实际网关写入 `deploy/ack/values-staging.yaml`，不能假定 nginx 注解适用于所有 MSE 网关。
- 多人使用时需验证按客户端 IP 的限流。若代理信任保持关闭，多位嘉宾可能共享网关 IP 并触发限制；应由 IT 配好可信真实 IP 头并验证，不能为了绕过限流直接信任任意来源头。
- 由 IT 配置存储保护、备份与运维。现有后台只有一个管理账号；没有员工角色权限或二次验证，不要将其描述为已实现。

## 上传到新项目

1. IT 创建私有项目并初始化 README，告诉你默认分支名和可用的 HTTPS/SSH 克隆地址。
2. 在**新建的干净目录**克隆该公司项目。不要从当前电脑的祖先 Git 目录直接 `git add .`，也不要整体搬运旧 GitHub 历史。
3. 创建 `codex/ack-deploy` 分支，将本包 `vip-reimburse-web/` 内的内容（包含 `.gitlab-ci.yml`、`.dockerignore`、`.gitignore`）复制到新项目**根目录**。
4. 只提交源码、Chart 和说明。不要复制本机 data、模型缓存、虚拟环境、导出材料、备份或 `.env`。
5. 提交并推送分支，创建 Merge Request。IT 核对目标和资源、补充网关注解；检查测试通过后合并默认分支。

此 CI 适用于独立仓库根目录布局，不是示例的多项目子目录布局。它会在 MR、默认分支提交及手动创建流水线时运行检查，不会只监听 `.gitlab-ci.yml` 的变化。

## 构建和手动发布

1. 打开 `Build → Pipelines`（旧版菜单可能叫 `CI/CD → Pipelines`）。
2. `python_checks` 运行虚构材料的后端测试；`helm_checks` 渲染并检查 Chart。它们无需集群凭据。
3. 合并默认分支后，`docker_build` 构建、实际检查 OCR 并推送 `vip-完整提交SHA` 镜像；模型下载或推理失败则构建失败。
4. 在 Container Registry 确认该标签存在。此时网站还未发布。
5. IT 完成配置并确认备份安排后，有发布权限的人点击 `deploy_to_kubernetes` 的播放按钮。该任务不会自动发布。
6. 脚本核对默认分支、目标空间、PVC、Secret 及 HTTPS 设置，再用 `helm upgrade --install --atomic --wait` 发布。临时 kubeconfig 不打印并在任务结束时删除。
7. 发布状态 Ready 后仍需下面的公网验收；CI 页面绿色不等于嘉宾已经可以访问。具体配置是否兼容公司 GitLab 版本，以项目里的 CI Lint 和实际流水线为准。

## 必须完成的目标环境验收

只用虚构嘉宾资料和虚构票据，确认：

1. 手机关闭飞连/VPN，用蜂窝网络在微信打开正式 HTTPS 首页，证书有效，无认证跳转。
2. 首页、静态素材、`/admin`、`/api/config` 正常，后台未登录不能访问记录与原文件。
3. 多位测试者独立验证邀请码、PDF/图片 OCR，核对税号、金额；接近 15MiB 的文件通过网关，超过上限的文件被拒绝。
4. 支付截图、多笔费用、银行卡/支付宝、自动草稿、刷新恢复、提交、手机号查询符合预期。
5. 管理端审核、Excel、票据 ZIP、删除和回收站恢复正常；其他嘉宾不能下载他人文件。
6. 重启 Pod，确认记录、票据、支付截图与草稿仍在；临时 OCR 缓存重新准备后可识别。
7. IT 完成一次备份到隔离空间的恢复演练，并核对申请数和原文件内容。备份必须在一致状态下包含整个 `/data`，不能只备份数据库或只导出票据。
8. 记录正式域名、维护人、备份频率、保留期限和停止收集日期，再向嘉宾发布网址/二维码。

## 更新和回退

先安排维护窗口并按 IT 流程制作一致备份，再走分支 → MR → 默认分支构建 → 手动发布。不删除 PVC，也不同时运行多个副本写入它。若没有支持一致快照的方案，可短暂停止应用后备份整个数据卷，再恢复服务。

`--atomic` 只回退 Kubernetes/Helm 资源，不会回退数据库和附件。更改数据库结构后，旧镜像不一定可直接使用；必要时由 IT 同步恢复数据库与文件到经过验证的状态。当前交付没有自动备份任务或已验证的云端恢复记录。

## 本次验证边界

本地可完成 Chart 渲染、Kubernetes 对象结构检查、部署脚本隔离测试和虚构资料后端测试。此电脑没有 Docker，无法证明 Linux 镜像构建和目标 ACK 运行成功；该部分必须以公司流水线及目标环境验收为准。首次云端数据库为空，本机资料不会自动上传或迁移。

参考：[公司发布示例](https://code.lingyiwanwu.net/examples/devops/-/blob/877208d249715fa6a29bdb3aded2a0d9d303fd91/example-apps/simple-python-app/.gitlab-ci.yml)。
