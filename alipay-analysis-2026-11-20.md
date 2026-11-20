# 支付宝小程序抓包分析（2026-11-20）

## 微信哈啰：沿用固定配置链接

### 补充主机解密后的复测

用户继续反馈广告存在。新日志覆盖 16:33:39–16:34:26，426109 字节，加载文件仍为 `AdBlock_SR.alipay-diagnostic.db`，MITM 列表包含新增的 m/cdn/abapi 三个主机；解密后观测到 `AppHellobikeWXSS/apmConfig.json`、微信端首页配置及业务请求，表明配置更新已生效。

- `adx.ssp.show` 六次查询均 REJECT，仍不足以认定所有微信广告均被覆盖。
- `platform.wx.popup.msg` 两次 DIRECT：16:33:55.190、16:34:08.254。微信端弹窗消息候选，但无响应体，不能确认全部为广告，拒绝可能影响业务通知。
- `homepage.banner.bubble.tip` 两次 DIRECT：16:33:55.011、16:34:07.848。首页气泡候选，但无响应体，不能确认与用户广告对应。
- `homepage.wechat.config`、`homepage.module.wechat`、`bottom.aggregation.tab.info`、登录与订单接口属于当前首页加载链路，不根据名字扩大封锁。

新样本仍未记录 HTTP 响应体。先确认用户看到的是开屏、底部商品还是弹窗/气泡，再选择单一候选做对照，不将两个接口同时称为已确认的广告接口。此次原始日志仅本机保存为 `capture-wechat-retest-log.txt`。

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
