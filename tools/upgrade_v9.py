#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v9 迁移：把 wximg 素材规则从「posid / sha256 精确匹配」升级为「整桶拒绝」。

背景：v8 已经覆盖样本里全部 75 次素材请求（52 posid + 23 sha256），但用户复测仍见
整屏广告。素材每轮都会换 fileid 与 sha256，精确规则永远追不上；同一个桶
`/141/20204/snscosdownload/` 在 6 份抓包 131 次请求里没有出现过一张非广告图，
所以改成按桶拒绝，覆盖以后所有新素材。

精确规则不删除，移动到 fragment-wechat-creatives-granular.conf，需要精细控制时切回去。
"""

import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONF = os.path.join(ROOT, 'AdBlock_SR.alipay-diagnostic.conf')
GRANULAR = os.path.join(ROOT, 'fragment-wechat-creatives-granular.conf')

WXIMG = '^https?://wximg\\.wxs\\.qq\\.com'

BUCKET_BLOCK = """# v9：整桶拒绝。6 份抓包里该桶 131 次请求全部是广告素材（18 张已逐张目视确认），
# 没出现过一张正常图片；素材每轮都换 fileid/sha256，精确规则追不上，所以按桶拦。
# 动作仍是 - reject-img：<image> 拿到 1 像素图只会留白，不会破图，也不触发重试。
# 如果出现正常图片变白（本样本里没出现过），把这一行注释掉并改用
# fragment-wechat-creatives-granular.conf 里的精确规则。
^https?://wximg\\.wxs\\.qq\\.com/141/20204/snscosdownload/ - reject-img
"""


def main():
    text = io.open(CONF, encoding='utf-8').read()
    lines = text.splitlines()
    section = None
    kept = []
    moved = []
    inserted = False

    for ln in lines:
        s = ln.strip()
        if s.startswith('[') and s.endswith(']'):
            section = s.strip('[]')
            kept.append(ln)
            continue

        if section == 'URL Rewrite' and s.startswith(WXIMG) and s.endswith('- reject-img'):
            moved.append(ln)
            continue

        # 原来的 posid 说明块里那几行注释跟着规则一起走，但保留一句指向新文件的提示
        if section == 'URL Rewrite' and s.startswith('# 微信哈啰开屏素材：'):
            continue

        kept.append(ln)

        # 桶规则插在 [URL Rewrite] 段头之后（第一个有效条目之前）
        if section == 'URL Rewrite' and not inserted:
            kept.append(BUCKET_BLOCK.rstrip())
            inserted = True

    io.open(CONF, 'w', encoding='utf-8', newline='\n').write('\n'.join(kept) + '\n')

    head = """# ============================================================
# 微信广告素材：精确规则（posid / sha256）备用版
#
# 主配置 AdBlock_SR.alipay-diagnostic.conf 现在按桶拒绝：
#   ^https?://wximg\\.wxs\\.qq\\.com/141/20204/snscosdownload/ - reject-img
# 这份文件是它的精细替代：只拦观测到的广告位与素材哈希，其余图片放行。
#
# 什么时候用：按桶拒绝后如果发现正常图片变白（6 份抓包里没出现过）。
# 怎么用：把主配置里那条整桶规则注释掉，再把下面这些行粘进 [URL Rewrite]。
# 注意：素材每轮换 fileid 与 sha256，这些规则只覆盖已观测到的素材，新素材不拦。
# ============================================================

[URL Rewrite]
"""
    io.open(GRANULAR, 'w', encoding='utf-8', newline='\n').write(head + '\n'.join(moved) + '\n')
    print('moved:', len(moved), 'bucket_rule_inserted:', inserted)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
