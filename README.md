# Shadowrocket 去广告配置

## 下载地址

```text
https://raw.githubusercontent.com/uefibin/shadowrocket-rules/main/AdBlock_Live.conf
```

## 使用步骤

1. Shadowrocket → **配置** → `+` → 粘贴上方链接下载并选中 `AdBlock_Live.conf`。
2. 点击配置右侧 `ⓘ` → **HTTPS 解密** → 开启并信任 CA 证书。
3. 首页「全局路由」选择 **配置**，重新连接。

## 支持拦截范围

### 通用开屏广告联盟 SDK
- 穿山甲 / GroMore（字节）
- 腾讯优量汇 / 广点通（GDT）
- 快手广告联盟
- 百度广告联盟（Mobads）
- 美数（MedProAd）、倍孜（BeiZi）、1RTB、FancyAPI / FancyDSP、FunLinkAds、快牛、阿里妈妈 Tanx、AdScope、小米广告

### App 与小程序

| 应用 | 拦截内容 |
| --- | --- |
| 哈啰小程序（支付宝 / 微信） | `adx.ssp.show` 开屏与广告下发、首页弹窗、回调与埋点 |
| 车来了小程序 | 信息流/详情页/预加载广告、底栏净化脚本（`chelaile.js`） |
| 中国移动 | 开屏初始化、广告位、首页弹窗、直播悬浮窗、挽留/Toast 弹窗、营销引擎、移动云盘广告 |
| 中国联通 | 广告域、首页弹窗、营销位 |
| 哔哩哔哩 | 开屏列表/展示接口、`-SPLASH.mp4` 视频开屏、商业化域、HTTPDNS |
| 网易云音乐 | `/xeapi/ad/*` 与 `/eapi/ad/*` 开屏及广告、推广弹窗、HTTPDNS |
| 夸克 | `splash.quark.cn` 开屏域、埋点 |
| 米家 | `openingBanner` 开屏横幅、埋点 |
| 山姆会员店 | 会员弹窗、浮窗 |
| 东方财富 | 广告域、推广域、HTTPDNS、埋点上报 |
| 新浪财经 | 新浪/微博广告域、信标与日志上报 |
| 菜鸟 / 淘宝 / 京东 / 小红书 / 百度地图 / 知乎 | 广告曝光、统计埋点与 HTTPDNS |
| 微信小程序 | 广告素材图（1px 透明替换）与监控上报 |

## 注意事项

- 部分 App（如中国移动）会把旧开屏配置保存在本地，需保持小火箭开启状态下卸载重装以清掉旧缓存。
- 微信小程序原生 5 秒封面广告壳子走 MMTLS 加密协议，代理层无法消除；可在微信开启「未成年人模式」并将小程序权限设为「全部」彻底关闭。
