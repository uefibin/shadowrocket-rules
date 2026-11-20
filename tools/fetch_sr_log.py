#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 Shadowrocket 内置 HTTP 日志服务抓流：
    http://<手机IP>:1082/api/log

实测行为（build 3488）：
  * 这是一个 chunked 的「一直不断开」的日志流，连上就开始吐；
  * 每次连接会把缓冲区里**当前这一轮**的日志从头重放一遍（本次抓包里是
    从 "system initialized" 开始），然后继续追加实时日志；
  * 服务端只接受有限个订阅者，浏览器里开着那个页面时，脚本可能拿不到数据，
    所以抓之前把手机浏览器/Safari 里那个标签页关掉；
  * 手机侧 Shadowrocket 断开 VPN 后端口就不监听了，会 Connection refused。

用法：
    python tools/fetch_sr_log.py                       # 默认抓 180 秒，落到 capture/
    python tools/fetch_sr_log.py --secs 600
    python tools/fetch_sr_log.py --host 192.168.95.2 --port 1082
    python tools/fetch_sr_log.py --until-ctrlc         # 一直抓，Ctrl+C 结束

结束时会打印落盘文件路径和行数，直接喂给 tools/parse_sr_log.py 分析。
"""

import argparse
import os
import socket
import ssl  # noqa: F401  (仅为了在需要时留口子)
import sys
import time
from datetime import datetime


def fetch_once(host, port, out_path, deadline, idle_timeout=45.0):
    """连一次，把数据写到 out_path（同一个文件里续写）。返回写入字节数。"""
    written = 0
    req = (f"GET /api/log HTTP/1.1\r\n"
           f"Host: {host}:{port}\r\n"
           f"User-Agent: sr-log-fetch/1.0\r\n"
           f"Accept: */*\r\n"
           f"Connection: close\r\n\r\n").encode()

    with socket.create_connection((host, port), timeout=8) as s:
        s.settimeout(idle_timeout)
        s.sendall(req)
        with open(out_path, 'ab') as fh:
            buf = b''
            header_done = False
            while True:
                if time.time() > deadline:
                    return written
                try:
                    chunk = s.recv(65536)
                except socket.timeout:
                    return written
                if not chunk:
                    return written
                if not header_done:
                    buf += chunk
                    if b'\r\n\r\n' in buf:
                        head, _, rest = buf.partition(b'\r\n\r\n')
                        if b'200' not in head.split(b'\r\n', 1)[0]:
                            sys.stderr.write('非 200 响应：%s\n' % head[:200].decode('latin1'))
                            return written
                        fh.write(rest)
                        written += len(rest)
                        header_done = True
                else:
                    fh.write(chunk)
                    written += len(chunk)
                    fh.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default=os.environ.get('SR_LOG_HOST', '192.168.95.2'))
    ap.add_argument('--port', type=int, default=int(os.environ.get('SR_LOG_PORT', '1082')))
    ap.add_argument('--secs', type=int, default=180)
    ap.add_argument('--until-ctrlc', action='store_true')
    ap.add_argument('--outdir', default=os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'capture'))
    ap.add_argument('--idle-timeout', type=float, default=45.0,
                    help='多久没有新数据就重连（秒）')
    a = ap.parse_args()

    os.makedirs(a.outdir, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    out = os.path.join(a.outdir, f'sr-{stamp}.log')
    deadline = float('inf') if a.until_ctrlc else time.time() + a.secs

    print(f'目标   http://{a.host}:{a.port}/api/log')
    print(f'落盘   {out}')
    print('提醒   手机浏览器里开着的那个日志页面先关掉，否则脚本抢不到数据')

    total = 0
    tries = 0
    try:
        while time.time() < deadline:
            tries += 1
            left = 'inf' if deadline == float('inf') else f'{deadline - time.time():.0f}s'
            try:
                n = fetch_once(a.host, a.port, out, deadline, a.idle_timeout)
                total += n
                print(f'[{datetime.now():%H:%M:%S}] 第 {tries} 次连接，收到 {n} 字节，剩余 {left}')
            except (ConnectionRefusedError, socket.timeout, OSError) as e:
                print(f'[{datetime.now():%H:%M:%S}] 第 {tries} 次连接失败：{type(e).__name__}: {e}'
                      f'（3 秒后重试；手机侧确认 Shadowrocket 在运行且 VPN 已连接）')
                time.sleep(3)
                continue
            if n == 0:
                time.sleep(2)
    except KeyboardInterrupt:
        pass

    size = os.path.getsize(out) if os.path.exists(out) else 0
    lines = 0
    if size:
        with open(out, 'rb') as fh:
            lines = fh.read().count(b'\n')
    print(f'\n结束。文件 {out}')
    print(f'大小 {size} 字节，{lines} 行')
    print(f'下一步：python tools/parse_sr_log.py "{out}" --hosts')
    return 0


if __name__ == '__main__':
    sys.exit(main())
