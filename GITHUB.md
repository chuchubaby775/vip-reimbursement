# 把网站源码放到 GitHub，再发布网站

当前上线方向已改为公司 GitLab → 镜像仓库 → ACK，优先阅读 [ACK_DEPLOY.md](ACK_DEPLOY.md)。以下 GitHub/Compose 步骤仅供其他环境参考，不是公司发布操作。

GitHub 用来保存源码和后续更新。这个项目需要 Python 后台、私有文件存储、SQLite 和 PaddleOCR，**GitHub Pages 无法运行完整网站**。只上传源码后，嘉宾还不能通过公网提交报销；需要接着在服务器部署，获得 HTTPS 网站地址。

## 一、下载并解压源码包

使用本次交付的「VIP报销网站源码.zip」，解压得到 `vip-reimburse-web` 文件夹。这个包不包含本机嘉宾记录、原始票据、备份、密码或 OCR 模型缓存。官方 OCR 模型在服务器构建时重新下载。

主要材料：

| 文件 | 用途 |
| --- | --- |
| `public/` | 嘉宾填报、进度查询及工作人员界面，含零一品牌素材 |
| `server.py`、`ocr.py` | 后台、数据管理、票据识别 |
| `requirements*.txt` | Python 依赖 |
| `Dockerfile`、`.dockerignore` | 构建包含 OCR 的容器，限制上传到构建器的内容 |
| `compose.yaml`、`deploy/Caddyfile` | 后台、持久数据卷及 HTTPS 代理 |
| `.env.example` | 服务器配置模板，没有管理员密码 |
| `.gitignore` | 排除数据目录、真实环境配置和本地缓存 |
| `DEPLOY.md` | 服务器发布、更新和备份说明 |
| `tests/`、`scripts/` | 自动验证及 OCR 模型准备工具 |

## 二、创建私有仓库

登录 [GitHub](https://github.com/)，点击右上角「+ → New repository」：

1. 仓库名可以填 `vip-reimburse`。
2. 可见性选择 **Private**。
3. 暂时不要勾选初始化 README、`.gitignore` 或 License，本项目已经带有说明和忽略规则。
4. 点击「Create repository」，保存页面显示的仓库地址。

公司代码与品牌素材优先放在公司认可的账号或组织下。仓库地址形如 `https://github.com/你的用户名/vip-reimburse.git`。

## 三、上传解压后的源码

推荐在终端上传，可以完整保留 `.gitignore`、`.dockerignore` 等隐藏文件。打开 Mac 终端，输入 `cd `（末尾有空格），把**刚解压的 `vip-reimburse-web` 文件夹**拖进终端，按回车。请使用交付的干净源码包。

逐行执行：

```sh
git init
git add .
git status --short
```

查看待上传文件，应只有源码、静态素材、文档、测试和部署配置。如果出现 `data/`、票据、数据库、`.env` 或备份，先停止上传并检查目录。确认后执行：

```sh
git commit -m "Initial VIP reimbursement website"
git branch -M main
git remote add origin https://github.com/你的用户名/vip-reimburse.git
git push -u origin main
```

将示例地址替换为自己的仓库地址。若提示未设置 Git 提交身份，按终端提示设置你的姓名和 GitHub 邮箱后重新提交。首次推送需要在 GitHub 官方登录流程或已配置的 SSH 中授权；不要把密码、Token 或私钥发到聊天里。也可用 GitHub Desktop「Add Existing Repository」添加刚解压的源码文件夹，提交后「Publish repository」并保持私有。

在 GitHub 仓库页面确认能看到 `server.py`、`public/`、`Dockerfile` 和 `compose.yaml`。不要在仓库 Settings 中启用 GitHub Pages 来代替后台部署。

## 四、连接服务器，生成正式网址

推荐使用大会认可的腾讯云、阿里云等 Linux 服务器。准备一台已装 Docker Engine 和 Compose 插件的服务器、一个指向服务器的域名，以及服务器访问权限；建议至少 2 核 4 GB，实际资源需求需试运行确认。内地服务器的域名服务按云服务商要求完成备案。

在服务器终端使用已授权的 GitHub 访问方式拉取私有源码：

```sh
git clone https://github.com/你的用户名/vip-reimburse.git
cd vip-reimburse
cp .env.example .env
chmod 600 .env
```

在服务器上编辑 `.env`，填写真实 `APP_DOMAIN` 和至少 12 位的独立 `ADMIN_PASSWORD`，邀请码默认 `01AI2026VIP`。`.env` 只保存在服务器，不提交 GitHub。然后：

```sh
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
```

首次构建会安装 OCR 并下载模型，耗时取决于服务器和网络。完成后使用 `https://你的域名/` 填报，`https://你的域名/admin` 登录工作人员后台。具体网络、数据卷、备份及发布验证见 [DEPLOY.md](DEPLOY.md)。

先使用虚构嘉宾和票据验证完整流程，确认图片 OCR、草稿、后台导出都正常，再把正式网址或二维码发给嘉宾。首次服务器部署使用空数据库；这个源码包不会自动迁移本机已经录入的记录。

## 交付状态

旧版源码已上传到私有 GitHub 仓库 `chuchubaby775/vip-reimbursement`，当前新 ACK 配置尚未推送到公司 GitLab 或部署到云端。旧历史可能仍包含已经从当前分支删除的运行数据；交接公司项目时使用干净源码包，不直接迁移旧历史。此电脑没有 Docker，Linux 镜像构建和上线需通过公司流水线验证。源码仓库地址与嘉宾网站地址是不同的地址。
