#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性维护脚本：把 v7 的素材拒绝升级为 v8（reject-img + posid 泛化）。

只动 [URL Rewrite] 段里指向 wximg.wxs.qq.com 的条目，其余内容逐行原样保留。
运行前后可用 tools/simulate_rules.py 回放验证覆盖率没变。
"""

import io
import os
import sys

CONF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    'AdBlock_SR.alipay-diagnostic.conf')

OLD_ACTION = ' - reject'
NEW_ACTION = ' - reject-img'
EXACT_POSID = 'posid=5060180989186180(?:[&#]|$)'
ANY_POSID = 'posid=[^&#]+(?:[&#]|$)'


def main():
    text = io.open(CONF, encoding='utf-8').read()
    lines = text.splitlines()
    out = []
    section = None
    rewritten = 0
    posid_done = False

    for ln in lines:
        s = ln.strip()
        if s.startswith('[') and s.endswith(']'):
            section = s.strip('[]')
            out.append(ln)
            continue

        if section == 'URL Rewrite' and 'wximg' in ln and s.endswith(OLD_ACTION):
            if EXACT_POSID in ln:
                posid_done = True
                out.append('# 观测到的广告位 ID 是 posid=5060180989186180（微信广告位，本轮抓包 92 次带此参数）。')
                out.append('# 这里不写死 ID：该素材桶上凡带 posid 的请求都按广告位处理，新广告位也能覆盖。')
                out.append('# 若复测发现正常图片被留白，把这一行的 posid 改回精确值即可。')
                out.append(ln.replace(EXACT_POSID, ANY_POSID)[:-len(OLD_ACTION)] + NEW_ACTION)
            else:
                out.append(ln[:-len(OLD_ACTION)] + NEW_ACTION)
            rewritten += 1
            continue

        out.append(ln)

    io.open(CONF, 'w', encoding='utf-8', newline='\n').write('\n'.join(out) + '\n')
    print('rewritten:', rewritten, 'posid_generalized:', posid_done)
    return 0


if __name__ == '__main__':
    sys.exit(main())
