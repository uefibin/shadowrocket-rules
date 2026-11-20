#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shadowrocket 配置 linter
------------------------
校验一个 .conf 里「静默失效」的几类问题 —— Shadowrocket 解析失败时不报错，
只会悄悄丢掉那条规则，所以必须离线自查。

用法：
  python lint_sr.py AdBlock_SR.slim.conf
  python lint_sr.py AdBlock_SR.slim.conf --online      # 同时探测远程规则集
  python lint_sr.py A.conf --compare B.conf            # 两个配置对比
"""

import sys
import os
import re
import argparse
import collections

BUILTIN_POLICIES = {
    "PROXY", "DIRECT", "TAILSCALE",
    "REJECT", "REJECT-DICT", "REJECT-ARRAY", "REJECT-200",
    "REJECT-IMG", "REJECT-TINYGIF", "REJECT-VIDEO",
    "REJECT-DROP", "REJECT-NO-DROP", "FINAL",
}

# Shadowrocket 接受的规则类型
RULE_TYPES = {
    "DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "DOMAIN-WILDCARD",
    "USER-AGENT", "URL-REGEX", "IP-CIDR", "IP-CIDR6", "IP6-CIDR", "IP-ASN",
    "RULE-SET", "DOMAIN-SET", "SCRIPT", "DST-PORT", "GEOIP", "FINAL",
    "AND", "NOT", "OR", "PROTOCOL", "PROCESS-NAME", "SRC-IP",
}

# QuantumultX 专有、Shadowrocket 不支持的类型 —— 出现在 .list 里就是坑
QX_ONLY_TYPES = {
    "HOST", "HOST-SUFFIX", "HOST-KEYWORD", "HOST-WILDCARD",
    "HOST-REGEX", "IP6-CIDR6",
}

IPRULE_TYPES = {"IP-CIDR", "IP-CIDR6", "IP6-CIDR", "IP-ASN", "GEOIP"}


def strip_inline_comment(line):
    """剥离行内注释：只有 '#' 前面是空白才算注释（避免误伤 URL 里的 #）。"""
    s = line.rstrip()
    for i, ch in enumerate(s):
        if ch == "#" and (i == 0 or s[i - 1] in " \t"):
            return s[:i].rstrip()
    return s


def parse(path):
    sections = collections.OrderedDict()
    cur = None
    with open(path, encoding="utf-8-sig") as f:
        raw_lines = f.read().splitlines()

    for lineno, line in enumerate(raw_lines, 1):
        s = line.strip()
        m = re.match(r"^\[(.+?)\]$", s)
        if m:
            cur = m.group(1).strip()
            sections.setdefault(cur, [])
            continue
        body = strip_inline_comment(line).strip()
        if not body:
            continue
        if cur is None:
            sections.setdefault("_preamble", []).append((lineno, body))
        else:
            sections[cur].append((lineno, body))
    return sections, raw_lines


def is_domain_rule(rt):
    return rt.startswith("DOMAIN") or rt in ("USER-AGENT", "URL-REGEX")


def is_ip_rule(rt):
    return rt in IPRULE_TYPES


def check(path, online=False):
    sections, raw_lines = parse(path)
    errs, warns, infos = [], [], []

    # ---------- 1. 代理组名 ----------
    groups = {}
    for lineno, body in sections.get("Proxy Group", []):
        name = body.split("=", 1)[0].strip()
        if name in groups:
            errs.append(f"[Proxy Group:{lineno}] 组名重复：{name}")
        groups[name] = lineno

    # ---------- 2. 规则逐条校验 ----------
    rules = sections.get("Rule", [])
    seen = {}
    strategy_use = collections.Counter()
    qx_hits = 0
    geoip_line = None
    reject_ip_lines = []
    ruleset_urls = {}

    for lineno, body in rules:
        if body.startswith("#"):
            continue
        fields = [x.strip() for x in body.split(",")]
        rt = fields[0].upper()

        if rt in QX_ONLY_TYPES:
            errs.append(f"[Rule:{lineno}] {rt} 是 QuantumultX 专有类型，Shadowrocket 会静默丢弃")
            qx_hits += 1
            continue

        if rt not in RULE_TYPES:
            errs.append(f"[Rule:{lineno}] 未知规则类型 {rt}：{body[:60]}")
            continue

        # 字段数
        if rt == "FINAL":
            if len(fields) != 2:
                errs.append(f"[Rule:{lineno}] FINAL 应为 2 段，实际 {len(fields)} 段")
            policy = fields[1]
        else:
            if len(fields) < 3:
                errs.append(f"[Rule:{lineno}] 规则少于 3 段：{body[:60]}")
                continue
            policy = fields[2] if rt in ("IP-CIDR", "IP-CIDR6", "IP6-CIDR") else fields[-1]
            # IP 规则允许第 4 段 no-resolve
            if len(fields) > 3 and rt in ("IP-CIDR", "IP-CIDR6", "IP6-CIDR"):
                if fields[3] not in ("no-resolve", "src"):
                    warns.append(f"[Rule:{lineno}] IP 规则第 4 段异常：{fields[3]}")
            elif len(fields) > 3 and rt not in ("IP-CIDR", "IP-CIDR6", "IP6-CIDR"):
                warns.append(f"[Rule:{lineno}] 多余字段（第 4 段起）：{body[:70]}")

        strategy_use[policy] += 1

        # RULE-SET URL
        if rt == "RULE-SET":
            if not fields[1].startswith("http"):
                warns.append(f"[Rule:{lineno}] RULE-SET 非 http(s) 地址：{fields[1][:60]}")
            else:
                ruleset_urls.setdefault(fields[1], lineno)

        if rt == "GEOIP" and geoip_line is None:
            geoip_line = lineno
        if rt in IPRULE_TYPES and "REJECT" in policy and geoip_line is None:
            reject_ip_lines.append(lineno)

        # 重复
        key = (rt, fields[1].lower() if len(fields) > 1 else "")
        if key in seen:
            warns.append(f"[Rule:{lineno}] 与第 {seen[key]} 行重复：{fields[0]},{fields[1]}")
        else:
            seen[key] = lineno

    # ---------- 3. GEOIP 顺序（最容易踩的坑）----------
    if geoip_line is not None:
        for lineno, body in rules:
            fields = [x.strip() for x in body.split(",")]
            if len(fields) >= 3 and fields[0].upper() in IPRULE_TYPES and "REJECT" in fields[2]:
                if lineno > geoip_line:
                    errs.append(
                        f"[Rule:{lineno}] 拒绝型 IP 规则排在 GEOIP,CN（第 {geoip_line} 行）之后，"
                        f"CN 的 IP 会先被直连，这条永远不生效")

    # ---------- 4. 策略引用 ----------
    undefined = []
    for pol, cnt in strategy_use.items():
        if pol in BUILTIN_POLICIES:
            continue
        if pol in groups:
            continue
        ci = [g for g in groups if g.lower() == pol.lower()]
        if ci:
            warns.append(f"策略名大小写不一致：规则用 '{pol}'（{cnt} 条），组定义是 '{ci[0]}'")
        else:
            undefined.append((pol, cnt))
    for pol, cnt in undefined:
        warns.append(f"策略 '{pol}'（{cnt} 条规则引用）在本文件内未定义 —— 若它来自订阅/节点名则正常")

    # ---------- 5. 结构 ----------
    for need in ("General", "Rule"):
        if need not in sections:
            errs.append(f"缺少 [{need}] 段")
    if not any(r[1].upper().startswith("FINAL") for r in rules):
        errs.append("[Rule] 中没有 FINAL 兜底")
    if "Proxy" in sections and all(b.startswith("#") for _, b in sections["Proxy"]):
        infos.append("[Proxy] 段存在但无有效内容，可以删掉")

    # ---------- 6. 统计 ----------
    active = [r for r in rules]
    total = len(raw_lines)
    ncomment = sum(1 for l in raw_lines if l.strip().startswith("#"))
    nblank = sum(1 for l in raw_lines if not l.strip())

    print(f"文件：{os.path.basename(path)}")
    print(f"总行数 {total}｜有效规则 {len(active)}｜注释 {ncomment}｜空行 {nblank}"
          f"（有效占比 {len(active) / max(total, 1) * 100:.0f}%）")
    print(f"代理组 {len(groups)} 个｜远程规则集 {len(ruleset_urls)} 个")

    # ---------- 7. 远程探测 ----------
    if online and ruleset_urls:
        print("\n探测远程规则集…")
        ok_kb, bad = 0, []
        try:
            import urllib.request
            import concurrent.futures as cf
            proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
            handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
            opener = urllib.request.build_opener(*handlers)

            def probe(item):
                url, lineno = item
                try:
                    req = urllib.request.Request(
                        url, method="GET",
                        headers={"Range": "bytes=0-0", "User-Agent": "lint"})
                    r = opener.open(req, timeout=40)
                    cr = r.headers.get("Content-Range") or r.headers.get("Content-Length") or "0"
                    return url, lineno, int(cr.split("/")[-1] or 0), None
                except Exception as e:
                    return url, lineno, 0, f"{type(e).__name__}: {e}"

            with cf.ThreadPoolExecutor(8) as ex:
                for url, lineno, size, err in ex.map(probe, ruleset_urls.items()):
                    if err:
                        bad.append((lineno, url, err))
                    else:
                        ok_kb += size
        except Exception as e:
            print(f"  探测跳过：{e}")
        else:
            print(f"  成功 {len(ruleset_urls) - len(bad)}／{len(ruleset_urls)}，总下载量约 {ok_kb // 1024} KB")
            for lineno, url, err in bad:
                errs.append(f"[Rule:{lineno}] 规则集拉取失败 {url.split('/main/')[-1]}：{err}")

    # ---------- 8. 输出 ----------
    print()
    if errs:
        print(f"错误 {len(errs)}：")
        for e in errs:
            print("  ✗", e)
    else:
        print("错误 0")
    if warns:
        print(f"\n警告 {len(warns)}：")
        for w in warns:
            print("  !", w)
    else:
        print("警告 0")
    if infos:
        print(f"\n提示 {len(infos)}：")
        for i in infos:
            print("  -", i)

    return 1 if errs else 0


def compare(a, b):
    """两个配置的量化对比。"""
    def stat(p):
        secs, raw = parse(p)
        rules = secs.get("Rule", [])
        urls = {f.split(",")[1] for _, f in rules
                if f.upper().startswith("RULE-SET,") and "," in f}
        return {
            "lines": len(raw),
            "rules": len(rules),
            "comment": sum(1 for l in raw if l.strip().startswith("#")),
            "sets": len(urls),
            "groups": len(secs.get("Proxy Group", [])),
        }

    sa, sb = stat(a), stat(b)
    print(f"{'':<16}{os.path.basename(a):>26}{os.path.basename(b):>26}{'变化':>12}")
    label = {"lines": "总行数", "rules": "规则条数", "comment": "注释行",
             "sets": "远程规则集", "groups": "代理组"}
    for k, name in label.items():
        va, vb = sa[k], sb[k]          # va = 第一个文件（通常是新版）
        delta = va - vb                # 显示「新相对旧」的变化
        pct = f"{delta / vb * 100:+.0f}%" if vb else "—"
        print(f"{name:<16}{va:>26}{vb:>26}{pct:>12}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Shadowrocket 配置 linter")
    ap.add_argument("conf")
    ap.add_argument("--online", action="store_true", help="探测远程规则集可达性与体积")
    ap.add_argument("--compare", metavar="OTHER", help="与另一个配置对比")
    args = ap.parse_args()

    if args.compare:
        return compare(args.conf, args.compare)
    return check(args.conf, args.online)


if __name__ == "__main__":
    sys.exit(main())
