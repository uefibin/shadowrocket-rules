#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用真实抓包回放验证规则：把 capture/*.log 里出现的每个请求，按 conf 的
[Rule] 顺序跑一遍「第一条命中生效」，打印每条请求最终被谁判成什么。

这不是真机替代品，但能在把规则粘到手机之前，先回答三个问题：
  1. 该拦的（广告 API）是不是真的拦到了；
  2. 不该拦的（登录、订单、支付、地图）有没有被误伤；
  3. URL-REGEX 规则在没有解密（看不到 path）时会不会误伤 —— 会跳过而不是乱拦。

用法：
    python tools/simulate_rules.py adblock-alipay-mp.conf capture/sr-xxx.log
    python tools/simulate_rules.py adblock-alipay-mp.conf capture/*.log --only-reject
    python tools/simulate_rules.py adblock-alipay-mp.conf capture/*.log --host api.hellobike.com
    python tools/simulate_rules.py adblock-alipay-mp.conf capture/*.log --diff 旧.conf
"""

import argparse
import glob
import os
import re
import sys
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_sr_log import parse as parse_log  # noqa: E402

DOMAIN_TYPES = {'DOMAIN', 'DOMAIN-SUFFIX', 'DOMAIN-KEYWORD', 'DOMAIN-WILDCARD'}
SKIP_TYPES = {'RULE-SET', 'DOMAIN-SET', 'SCRIPT', 'USER-AGENT', 'PROCESS-NAME',
              'DST-PORT', 'PROTOCOL', 'AND', 'NOT', 'OR', 'SRC-IP'}

REJECT_POLICIES = ('REJECT',)


def strip_comment(line):
    for i, ch in enumerate(line):
        if ch == '#' and (i == 0 or line[i - 1] in ' \t'):
            return line[:i]
    return line


def load_rules(path):
    """返回 [(lineno, type, value, policy, raw)]。片段文件没有 [Rule] 段头时按整段处理。"""
    rules = []
    section = None
    body_lines = []
    for lineno, raw in enumerate(open(path, encoding='utf-8-sig').read().splitlines(), 1):
        s = raw.strip()
        m = re.match(r'^\[(.+?)\]$', s)
        if m:
            section = m.group(1).strip()
            continue
        body = strip_comment(raw).strip()
        if not body:
            continue
        if section in (None, 'Rule'):
            body_lines.append((lineno, body, section))

    for lineno, body, sec in body_lines:
        parts = [p.strip() for p in body.split(',')]
        rt = parts[0].upper()
        if rt == 'FINAL':
            rules.append((lineno, 'FINAL', '', parts[1] if len(parts) > 1 else 'PROXY', body))
        elif len(parts) >= 3:
            pol = parts[2] if len(parts) >= 3 else ''
            rules.append((lineno, rt, parts[1], pol, body))
    return rules


REWRITE_REJECT = re.compile(r'^(?P<rx>.+?)\s+-\s*(?P<action>reject[\w-]*)\s*$', re.I)


def load_rewrites(path):
    """[URL Rewrite] 里以 `- reject` 结尾的条目。

    Shadowrocket 的重写在 `always-reject-url-rewrite = true` 时对其他路由模式也生效；
    这里按「重写优先于规则」回放，用于统计素材层拦截的覆盖率。
    返回 [(lineno, compiled_regex, raw)]，正则编译失败的条目跳过。
    """
    out = []
    section = None
    for lineno, raw in enumerate(open(path, encoding='utf-8-sig').read().splitlines(), 1):
        s = raw.strip()
        m = re.match(r'^\[(.+?)\]$', s)
        if m:
            section = m.group(1).strip()
            continue
        if section != 'URL Rewrite':
            continue
        body = strip_comment(raw).strip()
        if not body:
            continue
        mm = REWRITE_REJECT.match(body)
        if not mm:
            continue
        try:
            out.append((lineno, re.compile(mm.group('rx')), body))
        except re.error:
            continue
    return out

def compile_rule(rt, val):
    if rt == 'DOMAIN':
        v = val.lower()
        return lambda host, url: host == v
    if rt == 'DOMAIN-SUFFIX':
        v = val.lower()
        return lambda host, url: host == v or host.endswith('.' + v)
    if rt == 'DOMAIN-KEYWORD':
        v = val.lower()
        return lambda host, url: v in host
    if rt == 'DOMAIN-WILDCARD':
        v = val.lower().replace('.', r'\.').replace('*', '.*')
        rx = re.compile('^' + v + '$')
        return lambda host, url: bool(rx.match(host))
    if rt == 'URL-REGEX':
        try:
            rx = re.compile(val)
        except re.error:
            return None
        # 没解密就没有 URL，SR 同样匹配不到 —— 这里保持一致，跳过
        return lambda host, url: bool(url) and bool(rx.search(url))
    if rt == 'IP-CIDR':
        try:
            import ipaddress
            net = ipaddress.ip_network(val, strict=False)
        except Exception:
            return None
        return lambda host, url: _is_ip(host) and _in_net(host, net)
    return None


def _is_ip(h):
    return bool(re.fullmatch(r'\d{1,3}(\.\d{1,3}){3}', h))


def _in_net(h, net):
    import ipaddress
    try:
        return ipaddress.ip_address(h) in net
    except Exception:
        return False


def decide(rules, host, url, rewrites=None):
    """返回 (policy, lineno, raw)。

    URL 为空时 URL-REGEX 与 [URL Rewrite] 都自动跳过（没解密就没有 path，SR 同样匹配不到）。
    传了 rewrites 时按「重写先于规则」判定，命中记作 REWRITE-REJECT。
    """
    if rewrites and url:
        for lineno, rx, raw in rewrites:
            if rx.search(url):
                return 'REWRITE-REJECT', lineno, raw
    for lineno, rt, val, pol, raw in rules:
        if rt == 'FINAL':
            return pol, lineno, raw
        if rt in SKIP_TYPES:
            continue
        if rt == 'GEOIP':
            # 无法离线判定归属，按「不命中」处理并在报告里标注
            continue
        fn = compile_rule(rt, val)
        if fn is None:
            continue
        try:
            if fn(host, url):
                return pol, lineno, raw
        except Exception:
            continue
    return 'NONE', 0, '(未命中，落到配置后面/兜底)'


def collect(logs):
    """从抓包还原 [(host, url, rule_in_log)]。url 为空表示没解密。"""
    items = []
    for lg in logs:
        for st in parse_log(lg):
            host = st.sni or st.host or '?'
            urls = st.lookup_urls or [None]
            for u in urls:
                items.append((host, u, st.rule() or '-'))
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('conf')
    ap.add_argument('logs', nargs='+')
    ap.add_argument('--only-reject', action='store_true')
    ap.add_argument('--host')
    ap.add_argument('--diff')
    ap.add_argument('--quiet', action='store_true')
    ap.add_argument('--no-rewrite', action='store_true',
                    help='忽略 [URL Rewrite] 里的 - reject 条目（只看 [Rule]）')
    a = ap.parse_args()

    logs = []
    for pat in a.logs:
        logs.extend(glob.glob(pat) or [pat])

    rules = load_rules(a.conf)
    rewrites = [] if a.no_rewrite else load_rewrites(a.conf)
    other = load_rules(a.diff) if a.diff else None
    items = collect(logs)

    agg = OrderedDict()
    for host, url, _ in items:
        if a.host and a.host not in host:
            continue
        pol, lineno, raw = decide(rules, host, url, rewrites)
        key = (host, url or '(未解密,无 URL)')
        agg.setdefault(key, Counter())[(pol, lineno, raw)] += 1

    stat = Counter()
    print(f'配置   {a.conf}  ({len(rules)} 条规则, {len(rewrites)} 条 reject 重写)')
    print(f'抓包   {len(logs)} 个文件，{len(items)} 个请求，{len(agg)} 个唯一 (host,url)\n')

    if not a.quiet:
        print(f"{'HOST':<40}{'判定':<10}{'命中行':<8} URL")
        print('-' * 118)

    for (host, url), c in sorted(agg.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        (pol, lineno, raw), n = c.most_common(1)[0]
        stat[pol] += n
        if a.only_reject and not pol.startswith('REJECT'):
            continue
        if not a.quiet:
            u = url if url.startswith('http') else url
            print(f'{host:<40}{pol:<10}L{lineno:<7}{u[:60]}')
        if other is not None:
            p2, l2, r2 = decide(other, host, url)
            if (p2, l2) != (pol, lineno):
                stat[f'diff:{pol}->{p2}'] += 1

    print('\n判定统计：')
    for k, v in stat.most_common():
        print(f'  {k:<24}{v}')

    print('\n命中行排行（说明规则打得准不准）：')
    lines = Counter()
    for (host, url), c in agg.items():
        (pol, lineno, raw), n = c.most_common(1)[0]
        if lineno:
            lines[(lineno, raw)] += n
    for (lineno, raw), n in lines.most_common(20):
        print(f'  {n:>4}  L{lineno:<5}{raw[:96]}')

    rejects = [(h, u) for (h, u), c in agg.items()
               if c.most_common(1)[0][0][0].startswith('REJECT')]
    if rejects:
        print('\n会被拦掉的真实请求：')
        for h, u in sorted(rejects):
            print(f'  REJECT  {h:<38} {u[:80]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
