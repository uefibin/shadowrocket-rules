## v8：微信端广告归属已定位到「微信广告组件」，素材层改为留白

本轮把 6 份微信阶段抓包（`capture-wechat-log.txt`、`-retest`、`-v4`、`-v5`、`-v6`、`-popup-retest`，合计 2225 个请求 / 560 个唯一 (host,url)）一起回放，得到四条新结论。

### 1. 广告素材是微信客户端自己下的，不是哈啰页面下的

同一条日志里两种 UA 同时存在，而且图片请求没有 Referer：

| 请求 | UA | Referer |
| --- | --- | --- |
| `api.hellobike.com/api?...` | `Mozilla/5.0 (iPhone...) MicroMessenger/8.0.80(0x1800503d) NetType/WIFI Language/zh_CN` | 小程序页面地址 |
| `wximg.wxs.qq.com/141/20204/snscosdownload/...` | `WeChat/8.0.80.34 CFNetwork/3896.200.61 Darwin/27.2.0` | **无** |

`WeChat/... CFNetwork` 是微信客户端自身的网络栈，加上没有 Referer，说明这批图片是微信的广告组件去拉的，不是小程序 JS 里的 `<image src>`。

### 2. 广告素材只有一个桶、两种参数形态

```
wximg.wxs.qq.com/141/20204/snscosdownload/SZ/reserved/<fileid>?ck=..&m=..&sha256=..[&posid=..]
```

- 带 `posid` 的 92 次（广告位 ID `5060180989186180`）；
- 不带 `posid` 的 39 次（v7 靠 18 条 sha256 精确规则覆盖）；
- 没有任何第二种路径形态 —— 这个桶就是广告素材桶。

### 3. 容器是微信广告组件，抓包里能看到它的 UI 素材

`wxa.wxs.qq.com/images/wxapp/` 共 127 次，全部是广告组件的界面素材：`xmark_black.png`（关闭按钮 22）、`feedback_icon*.png`（反馈入口 45）、`image_cover2.png`（封面占位 22）、`linear_gradient*` / `linner_gradient*`（渐变遮罩 25）、`live_icon_2.png`（4）。这些素材只在广告渲染时加载，正常页面不加载。

所以残留的 6 秒开屏是**微信流量主 / 原生模板广告的容器**：素材走 HTTPS（能看见），广告配置走微信自己的加密通道（抓包里只有 MMTLS 与 mmtls 网关，看不到内容）。这也解释了为什么 v4 / v5 / v6 拦掉哈啰自己的 `adx.ssp.show`、`platform.wx.popup.msg` 之后开屏依然在 —— 那是另一个渠道。

### 4. v8 只做三件能验证的事，不承诺去掉开屏

1. **动作从 `- reject` 换成 `- reject-img`**（1 像素图）。`<image>` 拿到 404 会显示破图并可能重试，拿到 1 像素图只是留白，重试风暴也小。
2. **posid 规则泛化**：`posid=5060180989186180` → `posid=[^&#]+`。新广告位出现时不用再补哈希；若发现正常图片被留白，把这一行改回精确值即可。
3. **两个默认关闭的候选项**：`adx.ssp.callback`（曝光/点击回传，拦了广告还在屏上，只是不上报，且可能引发重试）、`homepage.mini.popup.window`（微信版弹窗，4 次，无响应体证据）。

明确写进配置、禁止拦的清单：`xmark_black.png`（拦了广告就关不掉）、`feedback_icon*.png`、`image_cover2.png`、渐变遮罩、`wxsnsdythumb.wxs.qq.com` 桶（实测取回的是黑色遮罩）。

### 5. 离线回放（`tools/simulate_rules.py`，本轮新增 URL Rewrite 覆盖统计）

```
配置   AdBlock_SR.alipay-diagnostic.conf  (49 条规则, 19 条 reject 重写)
抓包   6 个文件，2225 个请求

被拦的请求按主机与命中方式汇总：
  184  wximg.wxs.qq.com   posid
   64  wximg.wxs.qq.com   sha256
  116  api.hellobike.com  规则（adx.ssp.show / recommend.popUp）

判定分布：PROXY 1548 / DIRECT 506 / REWRITE-REJECT 124 / REJECT 47
```

被拦的全部命中广告桶与两条广告接口；`wxa.wxs.qq.com` 的 127 次 UI 素材、`wxsnsdythumb` 8 次、以及登录 / 订单 / 地图 / 配置请求一次都没命中。换 `- reject-img` 前后覆盖率完全一致（样本内 75/75），说明这次只是换了响应方式，没有放宽也没有扩大范围。

### 6. 到这里能做的都做完了

素材层已经全覆盖，剩下的 6 秒容器属于微信广告组件，HTTPS 层够不到。可选的路只有两条：接受「广告变留白但倒计时还在」，或者在小程序内关掉对应广告位（只有开发者能改，用户侧做不到）。继续换哈希、扩大封锁范围只会破坏 `wxa.wxs.qq.com` 的 UI 素材，让广告关不掉、白块盖住页面。
