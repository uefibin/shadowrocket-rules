#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
两次抓包的 A/B 对比：用来做「关掉某条拦截，看冒出来什么」这类实验。

典型用法（找广告素材到底从哪加载）：
    1. 先把 URL-REGEX ...adx.ssp.show 那条注释掉，重开小程序，抓 A 包；
    2. 把那条规则恢复，再抓 B 包；
    3. python tools/diff_capture.py A.log B.log --hosts
       → 「只在 A 里出现」的 host 就是广告带出来的素材/CDN，可以据此再补规则。

用法：
    python tools/diff_capture.py A.log B.log                 # host + URL 差异
    python tools/diff_capture.py A.log B.log --hosts          # 只看 host
    python tools/diff_capture.py A.log B.log --urls           # 只看 URL
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_sr_log import parse as parse_log  # noqa: E402


def bag(path):
    hosts, urls = {}, {}
    for st in parse_log(path):
        h = st.sni or st.host or '?'
        hosts[h] = hosts.get(h, 0) + 1
        for u in st.lookup_urls:
            urls[u] = urls.get(u, 0) + 1
    return hosts, urls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('a')
    ap.add_argument('b')
    ap.add_argument('--hosts', action='store_true')
    ap.add_argument('--urls', action='store_true')
    a = ap.parse_args()
    want_hosts = a.hosts or not a.urls
    want_urls = a.urls or not a.hosts

    ha, ua = bag(a.a)
    hb, ub = bag(a.b)
    print(f'A = {a.a}   hosts={len(ha)} urls={len(ua)}')
    print(f'B = {a.b}   hosts={len(hb)} urls={len(ub)}')

    if want_hosts:
        only_a = sorted(set(ha) - set(hb))
        only_b = sorted(set(hb) - set(ha))
        print(f'\n== 只在 A 出现的 host（A 里那次多出来的流量）{len(only_a)} 个 ==')
        for h in only_a:
            print(f'  {ha[h]:>4}x  {h}')
        print(f'\n== 只在 B 出现的 host {len(only_b)} 个 ==')
        for h in only_b:
            print(f'  {hb[h]:>4}x  {h}')

    if want_urls:
        only_a = sorted(set(ua) - set(ub))
        only_b = sorted(set(ub) - set(ua))
        print(f'\n== 只在 A 出现的 URL {len(only_a)} 个 ==')
        for u in only_a[:200]:
            print(f'  {ua[u]:>3}x  {u[:130]}')
        print(f'\n== 只在 B 出现的 URL {len(only_b)} 个 ==')
        for u in only_b[:200]:
            print(f'  {ub[u]:>3}x  {u[:130]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
