# 团队临时试用

无需购买云服务器。网站后台与 OCR 运行在这台 Mac 上，通过 Cloudflare Quick Tunnel 临时 HTTPS 网址供异地团队访问。界面是 HTML/CSS/JavaScript，提交、共享数据和后台由 Python 服务提供。正式大会持续使用仍建议部署到大会认可的服务器。

## 当前电脑启动

已在本机准备官方 cloudflared ARM64 程序，下载包与官方发布的 SHA-256 一致。程序保存在被忽略的 `.runtime/cloudflared`，不会打入源码包。换电脑需要重新从 [Cloudflare 官方发布页](https://github.com/cloudflare/cloudflared/releases) 安装对应系统版本并准备项目的 OCR 环境。

双击 `start-team-trial.command`，等待终端显示 `https://…trycloudflare.com`。团队用这个网址填报，工作人员使用同网址的 `/admin`。嘉宾邀请码默认 `01AI2026VIP`。工作人员密码只保存在本机 `.runtime/team-trial-access.txt`，不要转发给填报嘉宾。

电脑需要保持开机联网，勿合盖。启动器会在运行期间防止空闲休眠，不能防止关机、合盖、断网或系统更新。临时链接不保证持续可用；停止或重启后通常会生成新网址。微信与不同网络环境的可达性以实际打开为准。

## 数据与退出

试用数据独立保存在 `data/team-trial/`，第一次启动为空库；既有 `data/records.sqlite3` 和本机预览资料不会被发布。停止后，试用记录仍保留在本机，下一次启动可以继续使用。更换域名后浏览器 Cookie 不会跨域迁移，因此先前未提交草稿不保证通过新网址自动找回；已提交记录仍可由后台查看。

保留启动终端；按 Ctrl+C 结束时会同时关闭临时隧道和此试用服务。隧道日志和当前网址记录位于 `.runtime/team-trial-tunnel.log`、`.runtime/team-trial-status.json`。本机原有 8765、8766 服务使用各自数据，不受此启动器影响。

先用虚构票据与收款信息完成团队试用。访问流量经过 Cloudflare 的 HTTPS 代理，文件最终保存在这台电脑；正式收集真实嘉宾资料前由大会确认使用方式和数据管理。临时网址可以被转发，邀请码只发给参与试用的人。

后端只监听 `127.0.0.1:8770`，Cookie 使用 Secure、HttpOnly、SameSite=Strict；仅此隔离的隧道配置启用 `PROXY_IP_HEADER=CF-Connecting-IP`，使用 Cloudflare 覆盖的客户端 IP 限流。直接运行或公开后端端口时不要信任任意传入的代理头。
