#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
解析 Shadowrocket 实时日志流（http://IP:1082/api/log）落盘的原始 log。

真实日志格式（实测，build 3488 / iOS 27.2.1）：

    [16:16:57.589] tcp stream <7> mitm ssl handshake success => api.hellobike.com
    [16:16:57.589] tcp stream <7> mitm ssl request => POST /api?homepage.shortcut.scene.perception HTTP/1.1
    Accept-Charset: UTF-8                      <- 没有时间戳前缀的行 = 上一个请求的头部/正文
    referer: https://2017050407110255.hybrid.alipay-eco.com/.../index.html#pages/index/index
    Host: api.hellobike.com
    [16:16:57.589] tcp stream <7> async lookup rule url => https://api.hellobike.com/api?homepage.shortcut.scene.perception host => api.hellobike.com port => 443
    [16:16:57.590] tcp stream <7> tcp rule => {
    \tresult = DOMAIN-SUFFIX,hellobike.com,DIRECT,
    ...
    }

关键点：
  * `async lookup rule url` 那行带完整 URL（含 query），是做 URL-REGEX 规则的唯一可靠来源；
  * 头部行没有时间戳，靠这一点归属到「最近一条 mitm ssl request」；
  * 中文有 GBK->UTF8 二次编码，需要用 encode('gbk').decode('utf-8') 修。

用法：
    python tools/parse_sr_log.py capture/x.log                 # 全量分组报告
    python tools/parse_sr_log.py capture/x.log --hosts         # host 一览
    python tools/parse_sr_log.py capture/x.log --mp            # 只看小程序容器(hybrid.alipay-eco 等)
    python tools/parse_sr_log.py capture/x.log --urls          # 打印所有完整 URL
    python tools/parse_sr_log.py capture/x.log --grep adx
    python tools/parse_sr_log.py capture/x.log --json out.json
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict

TS = re.compile(r'^\[(\d{2}:\d{2}:\d{2}\.\d{3})\]\s?(.*)$')
REQ = re.compile(r'^(?:tcp|proxy) stream <(\d+)> (?:mitm ssl request|mitm http request) => '
                 r'(GET|POST|PUT|DELETE|HEAD|OPTIONS|PATCH|CONNECT|TRACE) (\S+) HTTP/([\d.]+)')
LOOKUP_URL = re.compile(r'^(?:tcp|proxy) stream <(\d+)> async lookup rule url => (\S+) host => (\S+) port => (\d+)')
START = re.compile(r'^(?:tcp|proxy) stream <(\d+)> start host => (\S+) port => (\d+)')
CONNECT = re.compile(r'^(?:tcp|proxy) stream <(\d+)> connect stream host => (\S+) port => (\d+)')
MITM_OK = re.compile(r'^(?:tcp|proxy) stream <(\d+)> mitm ssl handshake success => (\S+)')
SNI = re.compile(r'tls sniffer catch domain (\S+) => (\S+)')
RULE_HDR = re.compile(r'^(?:tcp|proxy) stream <(\d+)> tcp rule => \{')
RESULT = re.compile(r'^result = (.+)$')
KV = re.compile(r'^\t([a-z][a-z0-9 ]*) = (.*?)(?:,)?$')
REPLY = re.compile(r'^HTTP/[\d.]+ (\d{3})')
HDR = re.compile(r'^([A-Za-z][A-Za-z0-9_\-]*):\s?(.*)$')

AD_HINT = [
    'adx', 'ssp', 'advert', 'adsystem', 'adserver', 'adn', 'gdt', 'pangolin', 'pangle',
    'beizi', 'mintegral', 'applovin', 'unityads', 'vungle', 'ironsource', 'adcolony',
    'chartboost', 'tapjoy', 'splash', 'popup', 'pop-up', 'banner', 'interstitial',
    'reward', 'rewardvideo', 'launch', 'recommend', 'marketing', 'promotion', 'campaign',
    'coupon', 'lottery', 'signin', 'task', 'track', 'tracker', 'beacon', 'monitor',
    'analytics', 'umeng', 'sensors', 'shence', 'appsflyer', 'adjust', 'stat',
]

# 小程序容器 host 特征：支付宝小程序 = *.hybrid.alipay-eco.com / *.alipay-eco.com
# 微信小程序 = *.servicewechat.com；其他 H5 容器按需补
MP_HINT = ('hybrid.alipay-eco.com', 'alipay-eco.com', 'servicewechat.com', 'hybrid.alipay.com')


def fix_mojibake(s):
    try:
        return s.encode('gbk').decode('utf-8')
    except Exception:
        return s


class Stream:
    __slots__ = ('sid', 'host', 'port', 'sni', 'rules', 'reqs', 'hdr', 'status',
                 'lookup_urls', 't')

    def __init__(self, sid):
        self.sid = sid
        self.host = None
        self.port = None
        self.sni = None
        self.rules = []
        self.reqs = []          # [(method, path)]
        self.hdr = []           # [{...}] 与 reqs 等长
        self.status = None
        self.lookup_urls = []
        self.t = None

    def rule(self):
        return self.rules[0] if self.rules else None

    def referer(self):
        for h in reversed(self.hdr):
            if h.get('referer'):
                return h['referer']
        return ''

    def ua(self):
        for h in reversed(self.hdr):
            if h.get('user-agent'):
                return h['user-agent']
        return ''


def parse(path):
    streams = {}
    order = []
    cur = None            # 当前正在收 HTTP 头的 stream 对象
    in_rule = None
    pending_rule = None

    raw = open(path, 'rb').read().decode('utf-8', 'replace')
    for line in raw.splitlines():
        line = line.rstrip('\r')
        m = TS.match(line)
        if m:
            body = m.group(2)
            cur_hdr = None
        else:
            body = line
            cur_hdr = 'hdr'

        s = body.strip()

        def get(sid):
            nonlocal order
            st = streams.get(sid)
            if st is None:
                st = Stream(sid)
                streams[sid] = st
                order.append(sid)
            return st

        # 没有时间戳的行：要么是规则块的花括号内容，要么是 HTTP 头/正文
        if cur_hdr:
            if in_rule and pending_rule is not None:
                if s == '}':
                    in_rule = False
                    pending_rule = None
                    continue
                mm = RESULT.match(s)
                if mm:
                    pending_rule.rules.append(fix_mojibake(mm.group(1)))
                continue
            if cur is not None:
                mm = HDR.match(s)
                if mm:
                    k = mm.group(1).lower()
                    if k in ('host', 'referer', 'user-agent', 'origin',
                             'x-requested-with', 'content-type', 'content-length'):
                        cur.hdr[-1][k] = mm.group(2)
            continue

        mm = REQ.match(s)
        if mm:
            st = get(mm.group(1))
            st.reqs.append((mm.group(2), mm.group(3)))
            st.hdr.append({})
            cur = st
            in_rule = None
            continue

        mm = LOOKUP_URL.match(s)
        if mm:
            st = get(mm.group(1))
            st.lookup_urls.append(mm.group(2))
            if not st.host:
                st.host, st.port = mm.group(3), int(mm.group(4))
            cur = None
            continue

        mm = START.search(s)
        if mm:
            st = get(mm.group(1))
            st.host, st.port = mm.group(2), int(mm.group(3))
            cur = None
            in_rule = None
            continue

        mm = CONNECT.search(s)
        if mm:
            st = get(mm.group(1))
            if not st.host:
                st.host, st.port = mm.group(2), int(mm.group(3))
            cur = None
            continue

        mm = MITM_OK.search(s)
        if mm:
            st = get(mm.group(1))
            st.sni = mm.group(2)
            cur = None
            continue

        mm = SNI.search(s)
        if mm:
            ip, dom = mm.group(1), mm.group(2)
            for st in streams.values():
                if st.host == ip and not st.sni:
                    st.sni = dom
            continue

        mm = RULE_HDR.search(s)
        if mm:
            pending_rule = get(mm.group(1))
            in_rule = True
            cur = None
            continue

        if in_rule and pending_rule is not None:
            if s == '}':
                in_rule = False
                pending_rule = None
                continue
            mm = RESULT.match(s)
            if mm:
                pending_rule.rules.append(fix_mojibake(mm.group(1)))
                continue
            continue

        mm = REPLY.match(s)
        if mm and cur is not None:
            if not cur.status:
                cur.status = int(mm.group(1))
            continue

    return [streams[s] for s in order]


def summarize(streams, only_mp=False, grep=None):
    groups = defaultdict(lambda: {'conns': 0, 'rules': Counter(), 'refs': Counter(),
                                  'uas': Counter(), 'paths': Counter(), 'urls': Counter(),
                                  'status': Counter(), 'ports': set()})
    for st in streams:
        host = st.sni or st.host or '?'
        g = groups[host]
        g['conns'] += 1
        if st.port:
            g['ports'].add(st.port)
        if st.rule():
            g['rules'][st.rule()] += 1
        if st.status:
            g['status'][st.status] += 1
        ref = st.referer()
        if ref:
            g['refs'][ref] += 1
        ua = st.ua()
        if ua:
            g['uas'][ua[:60]] += 1
        for meth, p in st.reqs:
            g['paths'][p.split('?')[0]] += 1
        for u in st.lookup_urls:
            g['urls'][u] += 1
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('log')
    ap.add_argument('--json')
    ap.add_argument('--hosts', action='store_true')
    ap.add_argument('--urls', action='store_true')
    ap.add_argument('--mp', action='store_true', help='只看小程序容器流量')
    ap.add_argument('--grep')
    ap.add_argument('--min', type=int, default=1)
    a = ap.parse_args()

    streams = parse(a.log)
    groups = summarize(streams)
    print(f'# 文件: {a.log}')
    print(f'# stream: {len(streams)}   host: {len(groups)}')
    print(f'# 含完整 URL 的请求: {sum(len(s.lookup_urls) for s in streams)}')
    print(f'# 含明文 HTTP 的请求: {sum(len(s.reqs) for s in streams)}')

    if a.urls:
        allu = Counter()
        for st in streams:
            for u in st.lookup_urls:
                allu[(st.sni or st.host, u)] += 1
        for (h, u), n in sorted(allu.items(), key=lambda x: (-x[1], x[0][1])):
            if a.grep and a.grep.lower() not in u.lower():
                continue
            print(f'{n:>3}  {h:<42} {u}')
        return

    def is_mp(g):
        return any(any(k in r for k in MP_HINT) for r in g['refs'])

    rows = []
    for host, g in groups.items():
        if a.mp and not is_mp(g):
            continue
        text = ' '.join([host] + list(g['paths']) + list(g['urls']) + list(g['refs'])).lower()
        score = sum(1 for k in AD_HINT if k in text)
        hits = [k for k in AD_HINT if k in text]
        rows.append((host, g, score, hits, is_mp(g)))
    rows.sort(key=lambda r: (-r[2], -r[1]['conns']))

    if a.hosts:
        print(f"\n{'HOST':<46}{'conns':>6}{'mp':>4}{'ad':>4}  rule")
        for host, g, score, hits, mp in rows:
            if g['conns'] < a.min:
                continue
            r = g['rules'].most_common(1)[0][0] if g['rules'] else '-'
            print(f'{host[:45]:<46}{g["conns"]:>6}{"Y" if mp else "":>4}{score:>4}  {r[:52]}')
        return

    for host, g, score, hits, mp in rows:
        if g['conns'] < a.min:
            continue
        print('\n' + '=' * 80)
        print(f"HOST  {host}   port={','.join(map(str, sorted(g['ports'])))}  conns={g['conns']}"
              f"  {'[小程序]' if mp else ''}")
        if g['rules']:
            print(f"RULE  {g['rules'].most_common(1)[0][0]}")
            if len(g['rules']) > 1:
                print(f"      {dict(g['rules'])}")
        if g['status']:
            print(f"HTTP  {dict(g['status'])}")
        for ref, n in g['refs'].most_common(2):
            print(f"REF   [{n}] {ref[:145]}")
        for u, n in g['urls'].most_common(10):
            print(f"URL   [{n}] {u[:150]}")
        if not g['urls'] and g['paths']:
            print(f"PATH  {dict(g['paths'].most_common(6))}")
        if score:
            print(f"AD?   score={score} hits={hits}")

    if a.json:
        out = []
        for host, g, score, hits, mp in rows:
            out.append({'host': host, 'conns': g['conns'], 'ports': sorted(g['ports']),
                        'rule': g['rules'].most_common(1)[0][0] if g['rules'] else None,
                        'referers': g['refs'].most_common(5),
                        'urls': g['urls'].most_common(30),
                        'paths': g['paths'].most_common(10),
                        'status': g['status'].most_common(3),
                        'ad_score': score, 'ad_hits': hits, 'mini_program': mp})
        json.dump(out, open(a.json, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(f'\n# JSON: {a.json}')


if __name__ == '__main__':
    main()
