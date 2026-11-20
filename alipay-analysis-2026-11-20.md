# 支付宝小程序抓包分析（2026-11-20）

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
