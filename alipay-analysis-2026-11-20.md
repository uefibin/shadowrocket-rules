# 支付宝小程序抓包分析（2026-11-20）


## v9：v8 复测仍无效的原因已定位，素材层改成整桶拒绝

用户复测 v8 后仍见整屏广告。本轮用数据把「为什么无效」拆成两条可验证的事实，并把素材拦截做到能做到的极限。

### 判据一：素材是每轮轮换的活系统，不是过期缓存

| 抓包 | 时间 | 唯一 fileid | 与上一份重叠 | 新增 / 消失 |
| --- | --- | ---: | ---: | --- |
| `capture-wechat-v5-log.txt` | 16:58 | 37 | — | — |
| `capture-wechat-v6-log.txt` | 17:00 | 55 | 18 | +37 / −19 |

两分钟内素材换了三分之一以上。所以「清了缓存就好」这条路不成立，广告数据确实每轮都在重新下发。

### 判据二：素材请求在设备上确实被拒了，开屏照样出来

v6 那次抓包里，posid 规则已经生效：

```
proxy stream <139> reject => https://wximg.wxs.qq.com/141/20204/snscosdownload/...&posid=5060180989186180
```

同一次会话共 52 次素材请求被拒、43 次放行（那 43 次是不带 posid 的，v7 才补上）。也就是说规则在跑、请求被拦，用户看到的整屏广告没有变化。

结合 v8 已经确认的 UA 证据（素材由 `WeChat/8.0.80.34 CFNetwork` 下载、无 Referer，且与 `xmark_black` / `image_cover2` / 渐变遮罩这些广告组件 UI 素材同时出现），结论是：**6 秒容器是微信广告组件的原生渲染，素材拦截只影响画面内容，不影响容器出不出来**。这是 Shadowrocket 这一层能做到的边界。

### v9 做的唯一改动：按桶拒绝，不再追哈希

```
^https?://wximg\.wxs\.qq\.com/141/20204/snscosdownload/ - reject-img
```

依据：6 份抓包里这个桶出现 131 次请求，全部是广告素材（其中 18 张逐张目视确认），没有出现过一张正常图片。素材既然每轮换 fileid / sha256，就按桶拦，未来新素材自动覆盖。

- 动作仍是 `- reject-img`（1 像素图）：万一误伤正常图片，也只是留白，不会破图或触发重试；
- 原来的 posid / sha256 精确规则没有删，移到 `fragment-wechat-creatives-granular.conf`，出现误伤时切回去；
- 回放结果：微信 6 份抓包 2225 个请求，`REWRITE-REJECT` 从 124 升到 131（该桶全覆盖），规则层 REJECT 仍是 47（`adx.ssp.show` / `recommend.popUp`）；支付宝两份抓包零影响。

### 想要真的没有开屏，只有这两条路

1. **用支付宝里的哈啰，不用微信里的。** 支付宝版走哈啰自家 `adx.ssp.show`，那条已被规则拦住，你自己也反馈过「支付宝广告好像没了」。同一个小程序、同样的功能，换入口即可。
2. **让广告位本身关掉。** 微信广告组件是流量主广告，只有小程序开发者能在后台关掉对应广告位，用户侧没有开关。微信「个性化广告管理」只影响推荐相关性，不会减少广告位。

顺带两个可自查的点：

- 规则是否真的在生效：在手机日志里搜 `reject => https://wximg`，有就是生效；
- 曾经下载过的素材会留在微信自己的图片缓存里，做一次「微信 › 设置 › 通用 › 存储空间 › 清理缓存」再复现，可以排除旧素材干扰。

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

## v6 实测未去除开屏；v7 补充已确认的广告预览图

用户反馈 v6 无效。最新日志为 17:00:20–17:01:34，719984 字节；其中 52 次 wximg 广告位素材请求明确出现 reject，说明规则确实执行。另有 23 次 wximg 请求无 posid，包含 18 张不同的图片。

将这 18 张图片全部下载并逐张目视检查，均为广告的模糊预览图，包括朴朴水果食品促销、添可洗地机、金地楼盘、证券/基金营销图。它们无 posid，因此 v6 的广告位规则没有匹配这些图片。这是已证实的素材覆盖缺口，但不是“补齐就一定去除开屏”的证据。

v7 在同一配置新增 18 条精确资源 sha256 查询参数拒绝，限定 wximg 主机和原素材路径。与原 posid 规则一起，离线回放覆盖本次样本全部 75 次 wximg 素材查询；其他 363 次查询不命中这些图片规则。图片更新为不同内容时 sha256 改变，规则不会自动覆盖新图片；该限制比封锁整条微信图片路径更可控。

这仍只处理图片请求，未修改微信 MMTLS 下发的广告配置、倒计时或本地缓存。若材料被全部拒绝而倒计时容器仍显示，需要能访问广告配置响应的进一步证据；普通 Shadowrocket HTTPS 解密不能直接解开 MMTLS，不应继续承诺素材封锁能消除整个开屏。18 张图片仅留本机，提交内容只包含资源哈希与规则。

## v6：微信开屏素材与用户截图直接对应

用户提供微信哈啰的朴朴超市、贝壳找房整屏广告截图。最新日志时间覆盖 16:56:52–16:58:19，647157 字节，已确认 wximg 主机解密生效。

从日志中提取并实际取回了 wximg 图片。路径末尾为 `6af0ed6c00049efb296a1663a767bc1e0000008d00004eec` 的图片，其“金地启曜／龙华实验旁，93–130m²，大阳台飘窗采光优越／贝壳找房”文案、建筑和卡片背景与用户第二张截图直接对应；请求参数含 `posid=5060180989186180`。这构成素材来源证据，比仅按接口名称推测更直接。

同一 posid 的其他已检查资源包括贝壳图标、添可洗地机广告、朴朴橙子与红薯广告，以及配套背景。朴朴素材中已检查的橙子图片与截图第一张的促销内容不是同一版本，不将二者说成像素级匹配。原始图片和含资源校验参数的完整日志只留本机，不推送。

v6 在固定配置 `[URL Rewrite]` 中新增一条拒绝：同时限定 `wximg.wxs.qq.com`、`/141/20204/snscosdownload/` 路径、完整查询参数 `posid=5060180989186180`。查询参数允许位于任意位置，拒绝相同数字前缀但不同广告位。保留无此 posid 的微信图片、关闭按钮、头像及微信业务网关。`always-reject-url-rewrite` 开启以支持其他路由模式下的该重写；wximg 保持 MITM。

这是对已观测广告位的素材层拦截，尚未修改 MMTLS 下发的广告配置。可能触发加载失败后跳过，也可能只使广告图空白而倒计时仍在，不能提前宣称整个开屏已去除。若重开后仍显示已缓存图片，需要结合新日志区分缓存与规则未命中；不要求清空整个微信数据或重新安装。若同一 posid 被其他小程序复用，其相应广告素材也会受影响。

回滚只需注释 `[URL Rewrite]` 中含该 posid 的一行并重连。文件名与固定更新地址均保持不变。

## v4 已生效但微信开屏仍在：撤回无效候选，转向资源观测

用户复测后仍见启动整屏广告。16:42:46–16:43:19 的最新日志记录 `platform.wx.popup.msg` 一次明确命中 URL-REGEX REJECT，`adx.ssp.show` 三次 REJECT。这排除了“新增候选一直未命中”这个先前问题，但仍不能证明广告由何处下发。v5 删除微信 popup 候选在 Rule 与 URL Rewrite 两处的拒绝，恢复 always-reject-url-rewrite 为 false；支付宝原有两条规则保留。

本轮进一步实际下载并检查了两个候选图片：`m.hellobike.com/51791357da.gif` 是“扫一扫”动画按钮；记录里的 `wxsnsdythumb.wxs.qq.com/.../64896d500007a9ae0acc51d22c96970b0000008d00004eec` 是黑色渐变遮罩。二者都不是具体广告商品素材，不拦截它们。图片仅本机保存，不上传。

日志中 `wximg.wxs.qq.com` 有 12 次域名级查询，具体路径尚未解密。v5-resource-trace 仅将此精确主机加到 MITM，用于记录资源路径，不新增广告拒绝。微信原生组件可能经 MMTLS 下发内容，若仍无独立广告 URL，则现有 Shadowrocket 日志不足以制定精确规则。不能把所有 wximg、MMTLS 或 servicewechat 域名封锁来宣称解决。新增主机若造成微信图片异常，应从 hostname 删除 `wximg.wxs.qq.com` 并重连。

仍使用固定文件名 `AdBlock_SR.alipay-diagnostic.conf`。当前微信开屏问题未解决，需要这次资源观测结果及微信实际开屏截图来进一步对应请求与展示。

## 固定配置 v4-popup-rewrite 发布

用户要求直接更新文件并推送，继续使用 `AdBlock_SR.alipay-diagnostic.conf`。最近复测日志 16:37:20–16:38:01 中，`platform.wx.popup.msg` 三次仍命中 hellobike.com DIRECT，`adx.ssp.show` 六次 REJECT。因此前者新增规则尚未在日志中验证生效，不能据此判定其拦截一定无效，也不能仅凭 DIRECT 判定是更新缓存还是优先级问题。

本版在原有 URL-REGEX 之外，为同一精确接口补充 `[URL Rewrite]` 的 `- reject`，并启用 `always-reject-url-rewrite = true`，让该重写在其他路由模式也可执行。该开关含义见[配置维护者的说明](https://github.com/LOWERTOP/Shadowrocket/wiki/)。补充同一固定文件的 `update-url`，版本注释改为 `v4-popup-rewrite`，方便检查手机更新内容。

本次没有新增其他广告接口候选，未封锁整域；微信整屏广告仍待真机复测。若客户端根本未加载新内容，HTTP 重写同样不会生效，用户仍需更新同一配置并重连。若影响业务弹窗，需同时注释 `[Rule]` 与 `[URL Rewrite]` 中的两处 `platform.wx.popup.msg`，然后保存重连。

## 微信哈啰：沿用固定配置链接

### 补充主机解密后的复测

用户继续反馈广告存在。新日志覆盖 16:33:39–16:34:26，426109 字节，加载文件仍为 `AdBlock_SR.alipay-diagnostic.db`，MITM 列表包含新增的 m/cdn/abapi 三个主机；解密后观测到 `AppHellobikeWXSS/apmConfig.json`、微信端首页配置及业务请求，表明配置更新已生效。

- `adx.ssp.show` 六次查询均 REJECT，仍不足以认定所有微信广告均被覆盖。
- `platform.wx.popup.msg` 两次 DIRECT：16:33:55.190、16:34:08.254。微信端弹窗消息候选，但无响应体，不能确认全部为广告，拒绝可能影响业务通知。
- `homepage.banner.bubble.tip` 两次 DIRECT：16:33:55.011、16:34:07.848。首页气泡候选，但无响应体，不能确认与用户广告对应。
- `homepage.wechat.config`、`homepage.module.wechat`、`bottom.aggregation.tab.info`、登录与订单接口属于当前首页加载链路，不根据名字扩大封锁。

新样本仍未记录 HTTP 响应体。先确认用户看到的是开屏、底部商品还是弹窗/气泡，再选择单一候选做对照，不将两个接口同时称为已确认的广告接口。此次原始日志仅本机保存为 `capture-wechat-retest-log.txt`。

用户随后明确残留为“启动时整屏广告”。固定诊断配置新增且仅新增 `platform.wx.popup.msg` 的 URL-REGEX REJECT 做单变量试验；`homepage.banner.bubble.tip` 与首页模块保持放行。该候选可能承载其他弹窗消息，当前尚不能证明能消除整屏开屏。更新原配置链接、确认启用、重连并从后台退出微信后复现，需同时检查日志命中与实际界面。若无效或影响其他通知，注释这条 `platform.wx.popup.msg` 即可撤销，继续追查 MMTLS 或缓存渠道。

用户要求处理同名的微信哈啰小程序，并明确不要反复更改文件名。后续继续更新 `AdBlock_SR.alipay-diagnostic.conf` 这一固定下载链接。用户反馈支付宝广告“好像没了”，记录为单次测试结果，不据此宣称所有广告均已解决。

本次读取日志覆盖 16:28:25–16:31:02，约 855 KB。微信阶段自 16:30 左右开始，已观测到带 MicroMessenger User-Agent 的以下流量：

- 16:30:05.484、16:30:05.932、16:30:35.142：`abapi.hellobike.com:443`。
- 16:30:05.484：`cdn.hellobike.com:443`。
- 16:30:05.572：`m.hellobike.com:443`。

这些当时仅记录主机名，无法区分广告与业务路径。固定配置本次只将这三个精确主机加入 MITM，不新增拒绝规则。它们是否允许当前微信版本解密仍需复测；出现证书错误或小程序加载异常，应从 hostname 删除本次追加的三个主机后重连。

当前样本包含 112 次 `/mmtls/` 规则查询、22 次 `wxa.wxs.qq.com` 公共图片请求，没有观测到 gdt.qq.com、ugdtimg.com、pgdt.gtimg.cn、ad.qq.com 的独立广告网络查询。这只说明本批记录中未出现这些目标，不能推出广告一定走哪个渠道。

`wxa.wxs.qq.com` 的图片包括关闭按钮、反馈图标、遮罩及封面，封锁这些资源可能只破坏界面而不移除广告。微信加密网关同样不作为广告拒绝目标。MMTLS 本身保护业务数据，参见[微信团队协议说明](https://github.com/WeMobileDev/article/blob/master/%E5%9F%BA%E4%BA%8ETLS1.3%E7%9A%84%E5%BE%AE%E4%BF%A1%E5%AE%89%E5%85%A8%E9%80%9A%E4%BF%A1%E5%8D%8F%E8%AE%AEmmtls%E4%BB%8B%E7%BB%8D.md)。对上述三个业务主机补充普通 HTTPS 解密，不意味着能解开 MMTLS。

用户更新同一配置、确认 CA 与解密开启、重连后重新打开微信哈啰并复现广告，再读取日志判断是否出现具体接口。后续日志请求暂时超时，当前没有拿到这一改动后的记录；微信广告尚未解决。

## 第二次复测：旧两条拦截均生效，开屏仍出现

用户在加载 GitHub 试验配置后反馈广告依旧出现。本次重新读取同一日志接口取得 HTTP 200、278420 字节，日志起始 16:16:52，最后观测时间 16:17:42。原始记录保存在 Git 忽略的 `capture-retest-log.txt`。

- `adx.ssp.show` 三次规则查询均命中带结束边界的 URL-REGEX REJECT。
- `homepage.recommend.popUp` 两次规则查询均命中新增的 URL-REGEX REJECT。
- MITM 列表含 `api.hellobike.com`，哈啰请求已解密。因此不能将此次失败归因于用户未安装或未启用规则。
- 16:17:06.471，流 54 的 TLS SNI 为 `render.alipay.com`，当时只记录域名层连接，没有可判断用途的 URL 路径。这发生在第一条 `adx.ssp.show`（16:17:08.411）之前，是需进一步观测的启动连接，尚不能确认是开屏来源。

提供独立的 `AdBlock_SR.alipay-diagnostic.conf`，与原试验配置相比只追加 `render.alipay.com` 到 MITM 及诊断注释，保留原规则以便对照。没有添加新的广告拒绝规则。用户需选用这份诊断配置，保留已信任的 CA，重连后完整退出支付宝再进入哈啰，复现一次开屏，然后读取日志确定 render 的 URL。若解密导致正常页面打不开，立即切回原试验配置。

该域名也用于正常 H5 页面，见[支付宝官方 web-view 文档](https://github.com/AlipayDocs/open-docs/blob/main/mini/component/%E5%9F%BA%E7%A1%80%E7%BB%84%E4%BB%B6/%E5%BC%80%E6%94%BE%E7%BB%84%E4%BB%B6/web-view/web-view%20H5%20%E9%A1%B5%E9%9D%A2%E6%89%BF%E8%BD%BD.md)，不能将整个域名视为广告封锁。若新日志仍只有 TLS 连接，应继续检查协议和解密错误；若请求不再发生而广告仍展示，再查缓存或公共网关渠道。此次尚未取得广告内容响应，问题未解决。

数据源：用户提供的局域网接口 `http://192.168.95.2:1082/api/log`。本次直连取得 HTTP 200、约 669 KB、8791 行文本，时间覆盖 16:03:52–16:10:53。接口保持连接并持续输出，curl 到时退出不代表未获取日志。原始日志仅保留在被 Git 忽略的本机文件 `capture-log.txt`；其中包含身份与定位等字段，不放入分析报告。

这是 Shadowrocket 连接/规则日志与部分解密请求，并非完整双向 HTTP 响应抓包。此次能明确归属支付宝的小程序主要是哈啰（AppHellobikeAliSS）；不能据此推出适用于所有支付宝小程序的广告黑名单。

## 实际观测与处理

次数按 `async lookup rule url` 计数，表示规则查询次数，可能包含重试，不是广告展示次数。

| 接口 | 次数 | 证据与决策 |
| --- | ---: | --- |
| `api.hellobike.com/api?adx.ssp.show` | 5 | 16:03:59.129、16:04:00.166、16:04:13.604、16:04:13.872、16:04:40.441，均命中 URL-REGEX REJECT。请求日志含 impIds、device、app 等广告请求结构；后续错误上报中出现该接口 404。保留拦截。 |
| `api.hellobike.com/api?homepage.recommend.popUp` | 3 | 16:04:00.165、16:04:13.860、16:04:40.411，均命中 hellobike.com DIRECT。用户确认旧拦截下开屏仍出现，试验版启用此候选做对照；无响应体，未证明与截图对应。 |
| `marketingapi.hellobike.com/api?activity.app.usageScene` | 2 | 只确认请求存在，无法证明全域仅用于广告；不整域封锁。 |
| `apmgw.hellobike.com/metrics` | 5 | 请求包含运行日志、广告失败及业务事件。属于遥测，拦截并不等于去掉广告；此次保留。 |
| `api.hellobike.com/api?user.login.checkToken` | 4 | 登录链路，保留。 |
| `api.hellobike.com/api?alipay.unpay.order` | 3 | 未支付订单，保留。 |
| `hello-location-based-services.hellobike.com/api?hello.lbs.recommend.stops` | 3 | 推荐上车点/定位请求，不能因 recommend 一词当成广告。 |

其他 `homepage.coupon.mall.module`、`homepage.newWelfare.alipay`、`homepage.newblood.prizeList`、`homepage.combinations.module` 等请求可能混合优惠与业务组件，未看到响应体前不默认拒绝。日志中的连接关闭耗时本身不能证明业务失败。

## 旧规则需要纠正的地方

本次日志直接记录了以下 SNI：

- 16:03:55.922：`203.209.243.148` → `mgw.alipay.com`。
- 16:04:06.649：`203.209.243.12` → `mgw.alipay.com`。
- 16:03:56.366：`203.209.250.114` → `amdc-thirdparty.alipay.com`。
- 16:03:55.857：`203.209.243.38` → `aquic.alipay.com`。

所以不能因 IP 归属公司的名称而把 203.209.230/243/250 整个 /24 当广告拦截。`no-resolve` 仅控制规则检查时是否触发 DNS 解析，并不保证不会影响支付。旧 `adblock-alipay-captured.conf` 的宽泛 IP 拒绝已用当前保守规则替换。

本次哈啰业务已命中 DIRECT，不能继续声称这些连接正在落入 FINAL,PROXY。日志出现 198.18.* 假地址，电脑也有 Meta 接口，说明存在上游代理/假 IP 环境，但这不足以证明支付宝风控或定位异常的原因。

## 交付与使用

- `AdBlock_SR.alipay.conf`：从用户指定的 `AdBlock_SR.conf` 生成的完整配置，插入本次支付宝规则，MITM 仅新增 `api.hellobike.com`。修正原有规则策略名与组名大小写，并把 4 个 QuantumultX 远程列表引用改为同名 Shadowrocket 路径；远程列表实际可达性未在线验证。
- `fragment-alipay-current.conf`：只取规则时使用。插入已有 `[Rule]` 最前面，并在已有 `[MITM]` 的 `hostname` 追加 `api.hellobike.com`。
- 原始 `AdBlock_SR.conf` 保持不变；这次没有发布或修改手机配置。

HTTPS 路径规则需要 Shadowrocket HTTPS 解密及已安装、受信任的 CA。新完整配置不包含私钥，导入后需在手机上检查证书和解密开关。已有配置请保留已有 CA 字段。日志已证明当时哈啰请求可被解密，但不能保证未来版本兼容。不要为此扩大到所有支付宝网关解密。

用户补充了哈啰“精选推荐”整屏广告截图（带广告标识、跳过按钮、6 秒倒计时），并明确反馈旧规则下仍然出现。因此当前文件是两条接口均启用的试验版，不能称为已解决。截图时间 15:39 早于这批日志，不能直接建立时间对应关系。再次请求日志接口时未能建立连接，未取得这次反馈后的新增日志。

启用“配置”路由模式，彻底退出并重开哈啰小程序。先确认登录、地图、订单查询正常，再看开屏。`adx.ssp.show` 的拒绝已由现有日志验证，新增配置尚未在手机加载。新增 popUp 规则需复测并比较界面，可能同时移除优惠弹窗；出现异常即注释该行。两条规则均不应承诺删除页面占位，也不覆盖服务端混入业务响应的广告。若两条均显示 REJECT 而开屏仍在，需要针对一次重新启动抓取对应时段的请求及广告响应，继续区分缓存、公共网关或其他下发渠道，不能靠封锁整个支付宝域名试错。
