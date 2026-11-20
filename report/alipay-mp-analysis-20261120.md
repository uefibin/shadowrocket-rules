# 支付宝小程序去广告：本次抓包分析与规则依据

- 日期：2026-11-20
- 数据源：手机侧 Shadowrocket 实时日志流 `http://192.168.95.2:1082/api/log`
- 抓包窗口：`16:16:52` → `16:20:03`（约 3 分 10 秒，期间小程序首页刷新过一次）
- 原始落盘：`capture/probe-162003.log`（433 KB / 6659 行）、`capture/live-20261120-161919.log`（412 KB，同一缓冲区的另一份）
- 解析：`tools/parse_sr_log.py`；规则回放：`tools/simulate_rules.py`
- 产物：`adblock-alipay-mp.conf`（片段 v4）、`AdBlock_SR.slim.conf`（已合并同一批结论）

---

## 1. 这个端点是什么，以及它的三个坑

`/api/log` 是 Shadowrocket 内置的日志 HTTP 服务，不是抓包文件下载口：

| 行为 | 实测表现 | 影响 |
| --- | --- | --- |
| 长连接 chunked 流 | `Transfer-Encoding: chunked`，连上就不停地吐，永远不会正常结束 | 必须 `--max-time` 或自己掐；用 `Invoke-WebRequest` 会等到超时 |
| 每次连接重放缓冲区 | 新连接第一条总是 `system initialized, build => 3488`，然后从头重放再追实时 | 单次短抓也能拿到完整一轮，不用守很久 |
| 浏览器会抢占 | Safari 里开着那个页面时，脚本只能拿到 0 字节 | 抓之前先关掉手机上的标签页 |
| 端口会消失 | 期间多次 `Connection refused`（VPN 断开 / App 被挂起） | 抓包脚本必须能重连重试 |
| 中文会乱码 | `CF官方优选1` 被写成 `CF瀹樻柟浼橀€1`（GBK→UTF-8 二次编码） | 解析时要按字节反转码，否则策略名对不上 |

手机当前在跑的配置 **不是** 本仓库的 `AdBlock_SR.slim.conf`，日志显示加载的是
`AdBlock_SR.alipay.db`，且规则里出现了 `DOMAIN-KEYWORD,taobao,DIRECT`、
`DOMAIN-SUFFIX,cn,DIRECT` 这类本仓库没有的写法。也就是说，下面的结论是
「你的手机当前状态」的实测，不是对仓库文件的假设。

---

## 2. 抓包概览

165 条 TCP 流、49 个 host、141 条带完整 URL 的请求（其余是未解密的纯 TLS）。

| 流量归属 | 流数 | host 数 |
| --- | --- | --- |
| 支付宝小程序（哈啰，appid `2017050407110255`） | 51 | 8 |
| 支付宝本体 / 静态资源 / 阿里风控 | 44 | 14 |
| Apple 系统（APNs、iCloud、地图服务） | 58 | 19 |
| 淘系（`guide-acs.m.taobao.com` 等） | 5 | 3 |
| 高德定位 | 2 | 2 |
| 其他 | 5 | 4 |

小程序容器可以从 UA 和 referer 双重识别，这是「先过滤支付宝小程序」的判定依据：

```
User-Agent: ... Ariver/1.1.0 AliApp(AP/12.12.56.6000) Nebula ... AlipayClient/12.12.56.6000 ... XRiver/10.2.58.1
referer:    https://2017050407110255.hybrid.alipay-eco.com/2017050407110255/0.3.2611161653.14/index.html#pages/index/index
rule result: DOMAIN-SUFFIX,hellobike.com,DIRECT
```

`Ariver` / `Nebula` / `AlipayClient` = 支付宝小程序容器；`hybrid.alipay-eco.com` = 小程序 H5 容器；
`2017050407110255` = 哈啰出行的 appid。本次窗口里 **只有哈啰一个小程序在跑**。

---

## 3. 小程序接口清单（全部来自真实请求）

`api.hellobike.com`：35 条流、21 个唯一 URL、67 次请求。全部是 `POST /api?<方法名>`。

| 接口 | 次数 | 语义判断 | 处置 |
| --- | --- | --- | --- |
| `bottom.aggregation.tab.info` | 7 | 底部 tab 配置 | **不拦**（拦了导航消失） |
| `homepage.shortcut.scene.perception` | 5 | 场景感知 | 不拦 |
| `user.login.checkToken` | 4 | 登录态校验 | 不拦 |
| `user.platform.event.upload` | 4 | 埋点上报 | 可选（默认关） |
| `msg.user.has` | 4 | 消息是否存在 | 不拦 |
| `adx.ssp.show` | 4 | **开屏/插屏广告物料下发**（adx=广告交易平台，ssp=供给方平台） | **REJECT** |
| `msg.toast.user` | 3 | 服务端弹窗（营销 + 订单提醒混用） | 灰度 |
| `homepage.recommend.popUp` | 3 | **首页推荐弹层** | **REJECT** |
| `homepage.newWelfare.alipay` | 3 | 福利中心 / 新人礼包 | 灰度 |
| `applet.homepage.medal.activity` | 3 | 勋章活动 | 灰度 |
| `homepage.coupon.mall.module` | 3 | 券市（领券中心） | 灰度 |
| `homepage.grid.cornerMark` | 3 | 金刚位角标（红点/促销标） | 灰度 |
| `homepage.combinations.module` | 3 | 首页组合模块（可能混广告坑位） | 灰度（风险偏高） |
| `homepage.module.newAlipay` | 3 | 首页模块配置 | 不拦 |
| `homepage.alipay.config` | 1 | 首页配置 | 不拦 |
| `com.fee.facade.queryUnPaidOrdersAndRecommend` | 3 | 未支付订单 + 推荐（同一响应） | **禁止拦** |
| `ongoing.order.rec.data` | 3 | 进行中订单 | 禁止拦 |
| `user.order.ongoing.sum` | 3 | 订单数量角标 | 禁止拦 |
| `alipay.unpay.order` | 3 | 待支付订单 | 禁止拦 |
| `homepage.module.getVehiclePriceFloorInfo` | 1 | 车辆价格 | 不拦 |
| `authorizationCode.to.alipayUserId` | 1 | 授权码换用户 ID | 禁止拦 |

另外 8 个哈啰 host 只有域名层可见（未解密）：`apmgw`（支付网关）、`taxiapi`（打车）、
`hello-location-based-services`（定位）、`cdn`、`ip`、`abapi`、`mobileconfig-gateway`、`api`。
这些全部落 `DOMAIN-SUFFIX,hellobike.com,DIRECT`，行为正确。

### 关键证据（日志原文）

广告接口被拦时，Shadowrocket 会打一条 `reject =>`，这是最硬的证据：

```
[16:17:08.411] tcp stream <59> mitm ssl request => POST /api?adx.ssp.show HTTP/1.1
[16:17:08.411] tcp stream <59> async lookup rule url => https://api.hellobike.com/api?adx.ssp.show host => api.hellobike.com port => 443
[16:17:08.411] tcp stream <59> reject => https://api.hellobike.com/api?adx.ssp.show

[16:17:08.721] tcp stream <56> mitm ssl request => POST /api?homepage.recommend.popUp HTTP/1.1
[16:17:08.721] tcp stream <56> reject => https://api.hellobike.com/api?homepage.recommend.popUp
```

`adx.ssp.show` 这条在你手机上 **已经在拦**（说明之前的 URL-REGEX 生效了，没白写）。
所以本次真正新增的是：`homepage.recommend.popUp` 落进规则、两个风控域名的直连纠偏、
以及把 12 个「看着像广告其实不能拦」的接口写成清单留档。

---

## 4. 顺带修掉的一个真 bug：两个阿里风控域名在走代理

这是本次抓包里最有价值的发现，和广告无关，但更影响体验：

| host | 流数 | 手机上的实际结果 |
| --- | --- | --- |
| `mum.alibabachengdun.com` | 10 | `result = FINAL,PROXY # CF官方优选1` |
| `cdn.ynuf.aliapp.org` | 3 | `result = FINAL,PROXY # CF官方优选1` |

- `alibabachengdun.com` 注册方是杭州橙盾信息科技有限公司（阿里系，2022 年注册），
  承载风控 / 设备指纹类接口。
- `ynuf.aliapp.org` 是阿里 WebUMID 与无痕验证码的静态资源（`um.js`、`um.json`、`wu.json`），
  阿里云官方问答里把它列为「验证码加载失败时必须加白的域名」。

国内风控链路绕到境外节点，轻则验证码转圈，重则被判「网络环境异常」。这两条不需要解密、
也不需要拦，钉死直连即可：

```
DOMAIN-SUFFIX,alibabachengdun.com,DIRECT
DOMAIN-SUFFIX,aliapp.org,DIRECT
```

回放验证：这一改动让抓包里 13 次「本该直连却走了代理」的请求回到 DIRECT。

---

## 5. 为什么只能按 URL 拦

支付宝小程序里没有第三方广告 SDK 的域名流量 —— 抓包里一个都没有（没有穿山甲、优量汇、
TopOn/AnyThink 之类）。小程序跑不了原生 SDK，广告是「业务接口把广告数据下发 + H5 渲染」，
所以：

- **域名规则拦不住广告位**：广告和登录、订单、打车共用 `api.hellobike.com`；
- **能拦的粒度只有 URL**：`POST /api?adx.ssp.show` 这类 query 就是接口方法名；
- **URL-REGEX 依赖 HTTPS 解密**：没解密就看不到 path，规则不命中（不会误伤，但也不生效）。

规则里统一加了边界符 `(?:[&=#]|$)`，避免 `adx.ssp.show` 顺带把 `adx.ssp.showroom`
这类同前缀接口一起拦掉。这是本次相对旧版规则唯一的写法改进。

---

## 6. 规则回放验证（真实抓包 × 新规则）

`python tools/simulate_rules.py adblock-alipay-mp.conf capture/probe-162003.log`

```
判定统计：
  DIRECT                  76
  REJECT                   7

会被拦掉的真实请求：
  REJECT  api.hellobike.com   https://api.hellobike.com/api?adx.ssp.show
  REJECT  api.hellobike.com   https://api.hellobike.com/api?homepage.recommend.popUp
```

拦掉的 7 次请求里没有一条是业务接口；登录、订单、支付、打车、定位、tab、配置全部
落在 `DOMAIN-SUFFIX,hellobike.com,DIRECT`。

同样跑 `AdBlock_SR.slim.conf`（已合并本次结论）：

```
  DIRECT                  125
  PROXY                    65   ← 全是 Apple 系统流量，属预期
  REJECT                    7
  L119  DOMAIN-SUFFIX,alibabachengdun.com,DIRECT   10 次（原来走代理）
  L120  DOMAIN-SUFFIX,aliapp.org,DIRECT             3 次（原来走代理）
```

`python lint_sr.py AdBlock_SR.slim.conf` → 错误 0、警告 0。

---

## 7. 还没拿到的：广告素材到底从哪加载

本次抓包里所有广告接口都已被拦，**素材请求根本没发出去**，所以拿不到素材 CDN。
要拿到只有做一次 A/B：

1. 注释掉 `adx.ssp.show` 那条规则，重开小程序，抓 A 包（有广告）；
2. 恢复规则，再抓 B 包（无广告）；
3. `python tools/diff_capture.py A.log B.log --hosts`
   → 「只在 A 里出现」的 host 就是广告素材域名，再补 `IP-CIDR` 或 `DOMAIN` 规则。

在没有这一步之前，任何「广告素材 IP 段」都是猜的 —— 上一轮就是这么把
`203.209.243.228` 当素材拦掉，结果它是 `mgw.alipay.com`（支付宝网关），
小程序直接报网络异常。本次抓包再次印证：`203.209.243.104`、`203.209.243.148`、
`203.209.250.41` 的 SNI 全是 `mgw.alipay.com`。

```
[16:16:56.283] tcp stream <5> start host => 203.209.243.104 port => 443
[16:16:56.283] tcp stream <5> tls sniffer catch domain 203.209.243.104 => mgw.alipay.com
[16:16:56.283] tcp stream <5> tcp rule => { result = DOMAIN-SUFFIX,alipay.com,DIRECT, ...
```

---

## 8. 复现命令

```bash
# 1) 抓（手机开着 Shadowrocket，先把手机浏览器里那个 1082 页面关掉）
python tools/fetch_sr_log.py --secs 300

# 2) 看有哪些 host，谁在走代理、谁在走直连
python tools/parse_sr_log.py capture/sr-*.log --hosts

# 3) 只看小程序容器发出的流量
python tools/parse_sr_log.py capture/sr-*.log --mp

# 4) 列出所有完整 URL（含 query，做 URL 规则的原料）
python tools/parse_sr_log.py capture/sr-*.log --urls

# 5) 规则回放：新规则会不会误伤
python tools/simulate_rules.py adblock-alipay-mp.conf capture/sr-*.log

# 6) A/B 找素材域名
python tools/diff_capture.py capture/A.log capture/B.log --hosts
```

---

## 9. 预期效果与回滚

| 现象 | 预期 |
| --- | --- |
| 开屏「精选推荐」 | 不再出现（`adx.ssp.show` 已在拦） |
| 首页推荐弹层 | 不再弹出（`homepage.recommend.popUp`） |
| 验证码 / 滑块 | 加载更快、不再转圈（两个风控域名回直连） |
| 首页模块、tab、订单、打车、支付 | 不受影响 |

出问题就按这个顺序回退：先注释 `DOMAIN-SUFFIX,alibabachengdun.com` 与
`DOMAIN-SUFFIX,aliapp.org`（怀疑风控相关），再注释两条 URL-REGEX（怀疑广告位）。
B 段灰度项默认全关，不参与回退。
