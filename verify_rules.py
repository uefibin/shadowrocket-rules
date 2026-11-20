# -*- coding: utf-8 -*-
"""
Shadowrocket 规则离线校验器（无第三方依赖）

用法：
  python verify_rules.py lint               静态检查：语法 / 重复 / 冲突 / 遮蔽 / 顺序
  python verify_rules.py test gdt.qq.com    预测某个域名会命中哪一条规则
  python verify_rules.py selftest           跑内置断言用例

说明：
  这是一个"影子引擎"，按 Shadowrocket 的语义复刻匹配逻辑：
  从上到下逐条比对，第一条命中的规则生效。
  它不能替代真机，但能在真机上试之前把顺序错、拼错、被白名单遮蔽这类问题先排掉。
"""

import os
import sys

CONF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adblock-wx-alipay.conf")

KNOWN_TYPES = {
    "DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "DOMAIN-SET",
    "IP-CIDR", "IP-CIDR6", "GEOIP", "IP-ASN",
    "RULE-SET", "URL-REGEX", "USER-AGENT", "PROCESS-NAME",
    "DST-PORT", "SRC-IP", "FINAL",
}
KNOWN_POLICIES = {
    "REJECT", "REJECT-TINYGIF", "REJECT-DROP", "REJECT-NO-DROP",
    "DIRECT", "PROXY",
}
DOMAIN_TYPES = {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD"}


def parse(path):
    rules, errors, warnings = [], [], []
    section = None
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line.strip("[]").strip()
                continue
            if section != "Rule":
                continue

            parts = [p.strip() for p in line.split(",")]
            rtype = parts[0].upper()

            if rtype not in KNOWN_TYPES:
                errors.append((lineno, line, "未知规则类型 %r" % rtype))
                continue

            if rtype == "FINAL":
                if len(parts) < 2:
                    errors.append((lineno, line, "FINAL 缺少策略"))
                    continue
                rules.append({"lineno": lineno, "type": "FINAL",
                              "value": "", "policy": parts[1].upper(), "raw": line})
                continue

            if len(parts) < 3:
                errors.append((lineno, line, "字段不足，应为 类型,值,策略"))
                continue

            value = parts[1].lower()
            policy = parts[2].upper()

            if policy not in KNOWN_POLICIES:
                warnings.append((lineno, line, "策略 %r 不在标准集合内，请确认配置里有同名策略组" % policy))

            if rtype in DOMAIN_TYPES:
                if value.startswith("http") or "/" in value:
                    errors.append((lineno, line, "域名规则里出现了完整 URL，应该只写域名"))
                    continue
                if value.startswith("*") or value.startswith("."):
                    errors.append((lineno, line, "Shadowrocket 的 DOMAIN-SUFFIX 不需要写 * 或前导点"))
                    continue
                if " " in value:
                    errors.append((lineno, line, "域名中含空格"))
                    continue

            rules.append({"lineno": lineno, "type": rtype, "value": value,
                          "policy": policy, "raw": line})
    return rules, errors, warnings


def matches(rule, host):
    rtype, value = rule["type"], rule["value"]
    if rtype == "DOMAIN":
        return host == value
    if rtype == "DOMAIN-SUFFIX":
        return host == value or host.endswith("." + value)
    if rtype == "DOMAIN-KEYWORD":
        return value in host
    return False


def resolve(rules, host):
    host = host.lower().strip().rstrip(".")
    for rule in rules:
        if rule["type"] == "FINAL":
            return rule
        if matches(rule, host):
            return rule
    return None


def lint(rules, errors, warnings):
    # 1. 重复
    seen = {}
    for r in rules:
        key = (r["type"], r["value"])
        if r["type"] == "FINAL":
            continue
        if key in seen:
            prev = seen[key]
            if prev["policy"] != r["policy"]:
                errors.append((r["lineno"], r["raw"],
                               "与第 %d 行冲突：同一域名两种策略，实际生效的是第 %d 行"
                               % (prev["lineno"], prev["lineno"])))
            else:
                warnings.append((r["lineno"], r["raw"],
                                 "与第 %d 行重复，后一条永远不会生效" % prev["lineno"]))
        else:
            seen[key] = r

    # 2. 遮蔽：REJECT 规则是否被更靠前的规则先吃掉
    for i, r in enumerate(rules):
        if r["policy"] not in ("REJECT", "REJECT-TINYGIF", "REJECT-DROP"):
            continue
        if r["type"] == "DOMAIN-KEYWORD":
            continue
        probe = r["value"]
        for j in range(i):
            early = rules[j]
            if early["policy"] == r["policy"]:
                continue
            if early["type"] == "FINAL":
                continue
            if matches(early, probe):
                errors.append((r["lineno"], r["raw"],
                               "被第 %d 行 (%s) 遮蔽，这条拦截永远不会生效"
                               % (early["lineno"], early["raw"])))
                break

    # 3. 顺序：白名单是否都排在第一条拦截之前
    first_reject = next((i for i, r in enumerate(rules)
                         if r["policy"].startswith("REJECT")), None)
    if first_reject is not None:
        for i, r in enumerate(rules):
            if i > first_reject and r["policy"] == "DIRECT" and r["type"] in DOMAIN_TYPES:
                warnings.append((r["lineno"], r["raw"],
                                 "白名单出现在拦截规则之后，若与上面某条广告域名重叠会被抢先拦截"))

    # 4. 必须有兜底
    if not any(r["type"] == "FINAL" for r in rules):
        warnings.append((0, "", "没有 FINAL 兜底规则，未命中的流量行为取决于配置默认值"))
    return errors, warnings


def report(title, items):
    print("\n%s (%d)" % (title, len(items)))
    if not items:
        print("  无")
        return
    for lineno, raw, msg in items:
        loc = ("L%-3d " % lineno) if lineno else "     "
        print("  %s%s" % (loc, msg))
        if raw:
            print("        > %s" % raw)


SELFTEST = [
    # (host, 期望策略, 说明)
    ("gdt.qq.com", "REJECT", "广点通主域"),
    ("v2.gdt.qq.com", "REJECT", "广点通子域，靠 DOMAIN-SUFFIX 命中"),
    ("mi.gdt.qq.com", "REJECT", "激励视频接口"),
    ("e.qq.com", "REJECT", "腾讯广告落地页"),
    ("ad.qq.com", "REJECT", "微信广告组件"),
    ("pgdt.ugdtimg.com", "REJECT", "广告素材 CDN 子域"),
    ("pgdt.gtimg.cn", "REJECT", "广告图片 CDN"),
    ("pangolin-sdk-toutiao.com", "REJECT", "穿山甲"),
    ("pglstatp-toutiao.com", "REJECT", "穿山甲素材"),
    ("mobads.baidu.com", "REJECT", "百度联盟"),
    ("weixin.qq.com", "DIRECT", "微信本体不能被拦"),
    ("api.weixin.qq.com", "DIRECT", "微信 API 子域"),
    ("servicewechat.com", "DIRECT", "小程序基础库"),
    ("mmbiz.qpic.cn", "DIRECT", "微信图片"),
    ("tenpay.com", "DIRECT", "微信支付"),
    ("alipay.com", "DIRECT", "支付宝本体"),
    ("gw.alipayobjects.com", "DIRECT", "支付宝小程序静态资源"),
    ("alicdn.com", "DIRECT", "阿里 CDN"),
    ("qq.com", "NONE", "裸 qq.com 不被我们拦，验证没有过度拦截"),
    ("example.com", "NONE", "无关域名不命中，交给用户原有规则"),
]


def selftest(rules):
    ok = fail = 0
    print("\n自测用例")
    for host, expect, note in SELFTEST:
        hit = resolve(rules, host)
        got = hit["policy"] if hit else "NONE"
        passed = got == expect
        if passed:
            ok += 1
            print("  [PASS] %-26s -> %-8s %s" % (host, got, note))
        else:
            fail += 1
            print("  [FAIL] %-26s -> 期望 %-8s 实际 %-8s (%s)" % (host, expect, got, note))
            if hit:
                print("         命中行 L%d: %s" % (hit["lineno"], hit["raw"]))
    print("\n结果: %d 通过, %d 失败" % (ok, fail))
    return fail == 0


def main():
    if not os.path.exists(CONF):
        print("找不到配置文件: %s" % CONF)
        return 2

    rules, errors, warnings = parse(CONF)
    errors, warnings = lint(rules, errors, warnings)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "lint"

    if cmd == "test":
        hosts = sys.argv[2:]
        if not hosts:
            hosts = [l.strip() for l in sys.stdin if l.strip()]
        print("按当前规则预测（第一条命中生效）:")
        print("  %-38s %-10s %s" % ("HOST", "策略", "命中规则"))
        print("  " + "-" * 74)
        for h in hosts:
            hit = resolve(rules, h)
            if hit is None:
                print("  %-38s %-10s %s" % (h, "NONE", "(无规则命中)"))
            else:
                print("  %-38s %-10s L%d %s" % (h, hit["policy"], hit["lineno"], hit["type"]))
        return 0

    print("配置文件: %s" % CONF)
    print("解析到 %d 条规则" % len(rules))
    report("语法错误", errors)
    report("警告", warnings)

    if cmd == "selftest":
        passed = selftest(rules)
        return 0 if passed and not errors else 1

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
