"""Run an isolated team trial through a temporary Cloudflare HTTPS tunnel."""
from pathlib import Path
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server import create_server, DEFAULT_INVITE_CODE, now


def private_write(path, text):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as handle:handle.write(text)
    path.chmod(0o600)


def main():
    runtime = ROOT / '.runtime'
    binary = runtime / 'cloudflared'
    if not binary.is_file():
        raise SystemExit('缺少 .runtime/cloudflared，请先安装 Cloudflare 官方隧道程序。')
    runtime.mkdir(exist_ok=True)
    runtime.chmod(0o700)
    # This process serves only a dedicated empty-on-first-start trial directory.
    # The loopback port cannot be reached directly from the local network.
    os.environ['COOKIE_SECURE'] = '1'
    os.environ['TRUST_PROXY_HEADERS'] = '1'
    os.environ['PROXY_IP_HEADER'] = 'CF-Connecting-IP'
    os.environ.setdefault('GUEST_INVITE_CODE', DEFAULT_INVITE_CODE)
    data_dir = ROOT / 'data' / 'team-trial'
    server = create_server('127.0.0.1', 8770, data_dir)
    access = runtime / 'team-trial-access.txt'
    password = server.app.generated.get('管理员密码') or os.environ.get('ADMIN_PASSWORD')
    if password:
        private_write(access, f'团队试用版工作人员登录密码：{password}\n嘉宾邀请码：{os.environ["GUEST_INVITE_CODE"]}\n'
                      '不要转发工作人员密码给嘉宾；原始资料保存在 data/team-trial/。\n')
    elif not access.exists():
        print('工作人员请使用之前保存的密码。', flush=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):signal.signal(signum, lambda *_: stop.set())
    tunnel_log = runtime / 'team-trial-tunnel.log'
    private_write(tunnel_log, '')
    tunnel_config = runtime / 'team-trial-cloudflared.yml'
    private_write(tunnel_config, '{}\n')
    status_path = runtime / 'team-trial-status.json'
    status = {'pid':os.getpid(), 'startedAt':now(), 'dataDir':str(data_dir), 'url':'', 'running':True}
    private_write(status_path, json.dumps(status, ensure_ascii=False))
    tunnel = None
    keep_awake = None
    print('正在为团队试用版建立 HTTPS 链接…', flush=True)
    print(f'工作人员凭据仅保存在本机：{access}', flush=True)
    try:
        if sys.platform == 'darwin':
            keep_awake = subprocess.Popen(['/usr/bin/caffeinate','-i','-s','-w',str(os.getpid())])
        with tunnel_log.open('a') as output, tunnel_log.open('r') as reader:
            tunnel = subprocess.Popen([str(binary), '--config',str(tunnel_config),'tunnel','--no-autoupdate',
                                       '--url','http://127.0.0.1:8770','--protocol','http2',
                                       '--metrics','127.0.0.1:0'], stdout=output, stderr=subprocess.STDOUT)
            while not stop.wait(0.5):
                chunk = reader.read()
                match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', chunk)
                if match and not status['url']:
                    status['url'] = match[0]
                    private_write(status_path, json.dumps(status, ensure_ascii=False))
                    print('临时网址：'+status['url'], flush=True)
                    print('嘉宾邀请码：'+os.environ['GUEST_INVITE_CODE'], flush=True)
                    print('请保持电脑开机联网；按 Ctrl+C 停止。重启后网址通常会改变，已提交资料仍保留。', flush=True)
                if tunnel.poll() is not None:
                    raise RuntimeError(f'临时链接已断开，检查日志：{tunnel_log}')
    finally:
        if tunnel is not None and tunnel.poll() is None:
            tunnel.terminate()
            try:tunnel.wait(timeout=10)
            except subprocess.TimeoutExpired:tunnel.kill();tunnel.wait()
        if keep_awake is not None and keep_awake.poll() is None:
            keep_awake.terminate()
            keep_awake.wait(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        status['running'] = False
        private_write(status_path, json.dumps(status, ensure_ascii=False))


if __name__ == '__main__':main()
