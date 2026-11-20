# Shadowrocket 规则集

> **当前状态（v8-wechat-adunit，2026-11-20）**：手机在跑的固定文件名配置是
> `AdBlock_SR.alipay-diagnostic.conf`，下载地址不变：
> `https://raw.githubusercontent.com/uefibin/shadowrocket-rules/main/AdBlock_SR.alipay-diagnostic.conf`。
> v8 把微信素材拦截从 404 改成 1 像素图（`- reject-img`），并把 posid 规则泛化到任意广告位。
> **不承诺去掉微信 6 秒开屏**：证据见 [分析报告 v8 段](alipay-analysis-2026-11-20.md)，那层容器属于微信广告组件。
> 在用的完整试验配置是 `AdBlock_SR.alipay.conf`，只合并规则用 `fragment-alipay-current.conf`。
> `adblock-alipay-captured.conf` 的旧 IP 段拒绝已撤回；不要恢复 203.209.* 拦截。

## 当前哈啰开屏试验版：手机使用步骤

1. 在 Shadowrocket 的「配置」页添加远程配置，填入：

   ```text
   https://raw.githubusercontent.com/uefibin/shadowrocket-rules/main/AdBlock_SR.alipay.conf
   ```

2. 下载后点选 `AdBlock_SR.alipay.conf`，确认它成为当前启用配置（有勾选标记）。保留原配置，方便切回。
3. 点击该配置右侧的 ⓘ，进入「HTTPS 解密」并开启。新文件没有 CA 私钥；如果没有可用证书，生成 CA 并安装证书。
4. 安装证书时，进入 iPhone「设置 → 已下载描述文件」安装；再到「设置 → 通用 → 关于本机 → 证书信任设置」，开启对应 Shadowrocket CA 的完全信任。若已安装与当前配置匹配的 CA，无需重复生成。
5. 确认解密主机名包含 `api.hellobike.com`。本配置已写入该主机名；不要扩大到全部支付宝域名。
6. 回到首页，将「全局路由」设为「配置」，连接 Shadowrocket。完全关闭哈啰小程序后重新进入，检查 6 秒开屏、登录、地图和订单查询。

本版启用两条接口规则：`adx.ssp.show` 和试验项 `homepage.recommend.popUp`。前者已有日志命中证据，后者尚需真机确认；不保证已经消除开屏。若出现功能异常，可在配置编辑中给 `homepage.recommend.popUp` 的 `URL-REGEX` 行加 `#` 注释，再保存重连，或切回原配置。

若希望保留自己现有配置及 CA，仅将 [`fragment-alipay-current.conf`](fragment-alipay-current.conf) 中的有效规则插入已有 `[Rule]` 最前面，并将 `api.hellobike.com` 追加到已有 `[MITM]` 的 `hostname`。片段不能单独作为完整配置启用。

后续更新时，在「配置」页更新这份远程配置，再检查选中状态、HTTPS 解密开关与 CA。编辑远程配置生成的本地内容可能在下一次更新时被覆盖。

iOS Shadowrocket 的分流与去广告配置，针对**支付宝 / 微信内的小程序**做了实测优化。
规则里的每一条拦截都写明了依据，能查到来路；不是抄来的通用黑名单。

## 文件

| 文件 | 说明 |
| --- | --- |
| `AdBlock_SR.alipay-diagnostic.conf` | **手机在跑的固定文件名配置**，当前 v8-wechat-adunit（含微信素材层规则） |
| `AdBlock_SR.slim.conf` | 干净版完整配置，含分流策略组 + 去广告段（v4 结论已合并） |
| `AdBlock_SR.conf` | 上游原版（懒人配置），留作对比参考 |
| `AdBlock_SR.alipay.conf` | 从上游生成的支付宝试验版完整配置 |
| `adblock-alipay-mp.conf` | 支付宝小程序去广告片段 v4，抓包实测，可直接贴 |
| `alipay-analysis-2026-11-20.md` | 逐轮抓包分析记录，**v8 段是微信端结论** |
| `report/alipay-mp-analysis-20261120.md` | 支付宝抓包分析报告：接口清单、广告判定、证据原文 |
| `lint_sr.py` | 配置校验器，改完先跑它 |
| `adblock-alipay-captured.conf` | 早期支付宝小程序抓包片段（已被 v4 取代，留档） |
| `adblock-wx-alipay.conf` | 微信/支付宝通用广告域名片段 |
| `adblock.list` | 纯域名清单，适合并入已有配置 |
| `verify_rules.py` | 早期规则引擎，可模拟某域名命中哪条（`lint_sr.py` 更全面，保留作互补） |

### 工具（`tools/`）

从手机的 Shadowrocket 日志流 `http://<手机IP>:1082/api/log` 抓包 → 解析 → 回放验证，
是一条闭环。四个脚本都不需要第三方依赖。

| 脚本 | 作用 |
| --- | --- |
| `tools/fetch_sr_log.py` | 抓流。自动重连、限时、按会话落盘到 `capture/` |
| `tools/parse_sr_log.py` | 解析。还原成一条流 = 一条连接，输出 host / 规则命中 / 完整 URL / referer |
| `tools/simulate_rules.py` | 用真实抓包回放规则（含 `[URL Rewrite]` 的 `- reject*` 条目），逐条给出判定 |
| `tools/diff_capture.py` | 两次抓包的 A/B 差异，用来找广告素材域名 |
| `tools/upgrade_v8.py` | 一次性迁移脚本：v7 的 `- reject` 升到 `- reject-img` 并泛化 posid |

```bash
python tools/fetch_sr_log.py --secs 300          # 抓 5 分钟
python tools/parse_sr_log.py capture/sr-*.log --hosts
python tools/parse_sr_log.py capture/sr-*.log --urls
python tools/simulate_rules.py AdBlock_SR.alipay-diagnostic.conf capture-wechat-v6-log.txt
python tools/diff_capture.py capture/A.log capture/B.log --hosts
```


## 使用

### 方式一：整个配置导入（会替换当前配置）

Shadowrocket › 配置 › 添加 › 输入 URL：

```
https://raw.githubusercontent.com/uefibin/shadowrocket-rules/main/AdBlock_SR.slim.conf
```

**节点不受影响。** 服务器列表是独立存放的，导入配置只换配置本身，不会删你的节点或订阅。
代理组会自己从你已有的节点里建出来：

- `PROXY` 是 Shadowrocket 内置策略，代表「当前选中的节点」，不需要 `[Proxy]` 段。
  日志里 `FINAL,PROXY # CF官方优选1` 就是这个意思。
- `香港节点` / `美国节点` 等 6 个地区组用的是
  `policy-regex-filter=🇭🇰|HK|香港|…`，按关键词从你的节点里自动筛选，节点叫什么都行。

**会被整段覆盖的只有配置内的这几段**：`[General]`、`[Host]`、`[URL Rewrite]`、`[MITM]`。
其中 `[MITM]` 值得看一眼 —— 如果你原来的配置里还有别的主机名，导入后就只剩本文件的。

本文件 MITM 开的是 `*.google.cn` 和 `*.hellobike.com`。后者是必须的：
不解密 HTTPS 就只能看到域名、看不到 path 和 query，`adx.ssp.show` 那条 URL 规则等于没写。

原配置不会丢，配置列表里随时可以切回去。

### 方式二：只取规则段

用 `adblock-alipay-mp.conf`（v4）：整段复制，粘到你现有配置 `[Rule]` 的**最上面**。
撤销就整段删掉。

改动范围最小，适合只想加几条规则、不想动其余部分的情况。
`fragment-alipay-hellobike.conf` 是它的前身，保留作对比。

顺序不能改，原因见下。

## 维护

```bash
python lint_sr.py AdBlock_SR.slim.conf            # 语法、策略名、顺序、重复
python lint_sr.py AdBlock_SR.slim.conf --online   # 另加远程规则集可达性探测
python lint_sr.py 新.conf --compare 旧.conf        # 两版量化对比
python tools/fetch_sr_log.py --secs 300           # 真机抓包
python tools/simulate_rules.py adblock-alipay-mp.conf capture/*.log   # 抓包回放
```

`--online` 走系统代理；需要时设 `HTTP_PROXY` 环境变量。

## 微信小程序：6 秒开屏为什么拦不掉

同一个小程序（哈啰）在微信里和在支付宝里是两套广告渠道，这是本次排查最花时间的结论：

| | 支付宝内 | 微信内 |
| --- | --- | --- |
| 广告下发 | `api.hellobike.com/api?adx.ssp.show`，可解密、可 URL 拦截 | 微信广告组件（流量主），配置走加密通道，HTTPS 层看不到 |
| 广告素材 | 自家或阿里 CDN | `wximg.wxs.qq.com/141/20204/snscosdownload/...`，由微信客户端下载 |
| 能拦到哪一层 | 接口（广告直接不返回） | 只有素材（广告变留白，6 秒容器仍在） |

判定素材是「微信客户端自己下的」而不是小程序页面下的，靠的是同一条日志里两种 UA 并存：

- 小程序业务请求：`MicroMessenger/8.0.80 ... Mobile/15E148`，带 Referer；
- 素材请求：`WeChat/8.0.80.34 CFNetwork/3896.200.61`，**没有 Referer**。

同时 `wxa.wxs.qq.com/images/wxapp/` 出现 127 次广告组件的 UI 素材（关闭按钮 `xmark_black.png`、反馈图标、封面占位、渐变遮罩）—— 这些只在广告渲染时加载。**这些 UI 素材绝对不要拦**，拦了只会让广告关不掉或白块盖住页面。

v8 因此在素材层只做两件稳妥的事：

```
# 动作用 1 像素图，不用 404：<image> 拿 404 会破图并重试
^https?://wximg\.wxs\.qq\.com/141/20204/snscosdownload/[^?#]+\?(?:[^&#]*&)*posid=[^&#]+(?:[&#]|$) - reject-img
```

- posid 从写死的 `5060180989186180` 泛化为任意值，新广告位不用再补哈希；
- 无 posid 的 18 张广告预览图仍按 `sha256=` 精确拒绝（换图即失效，这是可接受的取舍）。

离线回放 6 份微信抓包（2225 个请求）：被拦的只有广告桶 184(posid)+64(sha256) 和两条哈啰广告接口 116，`wxa.wxs.qq.com` 的 UI 素材与登录/订单/地图/配置请求零命中。

## 踩过的坑

这个仓库有一半的价值在这些结论上，都是实测出来的：

**1. blackmatrix7 的 `QuantumultX/` 目录不能直接给 Shadowrocket 用。**
那些 `.list` 用的是 `HOST-SUFFIX` / `HOST` / `HOST-KEYWORD` 等 QuantumultX 专有类型，
Shadowrocket 一条都不解析，而且**不报错**，静默丢弃。实测 `Global.list` 36014 条里
只有 165 条能被识别，剩下 35849 条白下载。一律换 `Shadowrocket/` 同名版：
体积从 1188KB 降到 6KB，规则反而从「几乎全废」变成「全部生效」。

**2. 拒绝型 IP 规则必须排在 `GEOIP,CN,DIRECT` 之前。**
`GEOIP,CN` 会把所有归属 CN 的 IP 判为直连。广告 IP 也在 CN，
放到 GEOIP 后面就永远走直连，`REJECT` 一次都不会触发。`lint_sr.py` 把这条做成硬错误。

**3. 判断一个 IP 是不是广告，要看它承载的 SNI，不要看归属公司。**
曾把 `203.209.230/243/250.0/24` 当成广告素材段（归属「杭州阿里巴巴广告有限公司」），
用 `IP-CIDR ...,REJECT` 拦掉。实测日志里 `203.209.243.228` 的 SNI 是 `mgw.alipay.com`
—— 支付宝网关。拦它等于掐掉支付网关，App 直接报「网络异常」。
同一个 /24 里可以既有广告素材又有支付网关，归属公司说明不了用途。

**4. 域名解析成 fake-ip 时，`GEOIP,CN,DIRECT` 接不住。**
`api/cdn/ip/taxiapi/apmgw/abapi.hellobike.com` 全都解析成 `198.18.1.x`，
GEOIP 判不出归属，于是一律落到 `FINAL,PROXY` 走了代理节点。
支付宝检测到出口 IP 变化就判「网络环境异常」。国内 App 的关键域名必须显式写
`DOMAIN-SUFFIX,...,DIRECT`，不能指望 GEOIP 兜底。

**5. 同域名下的广告，只能按 URL 拦，而且需要 HTTPS 解密。**
哈啰的开屏广告由 `POST https://api.hellobike.com/api?adx.ssp.show` 下发，
和登录、下单共用同一个域名。域名规则区分不了，只能：

```
URL-REGEX,^https?://api\.hellobike\.com/api\?adx\.ssp\.show,REJECT
```

`URL-REGEX` 依赖解密才能看到路径；没解密时不匹配，请求会落到后面的直连（不会误伤）。
这条必须在 `DOMAIN-SUFFIX,hellobike.com,DIRECT` **之前**，否则白名单先命中就放行了。

**6. 微信拦不了 HTTPS 层。**
微信走 MMTLS、支付宝走 mPaaS，都有证书固定。对它们开 HTTPS 解密 =
支付失败 / 登录异常 / 风控提示。只能在域名和 IP 层 REJECT，效果相当于弱网，风控基本无感。

**7. 策略名大小写别赌。**
原文件规则写 `YOUTUBE`、组定义写 `YouTube`，靠 SR 大小写不敏感才没出错。不该依赖这种运气。

**8. 判断「能不能拦」，看看规则是谁在替你判 —— 但只看名字会翻车。**
本次抓包里 12 个接口名字都像营销位（`homepage.newWelfare`、`coupon.mall.module`、
`medal.activity`、`msg.toast.user`），实际全都承载业务数据，拦了小程序缺数据。
反过来 `adx.ssp.show`、`homepage.recommend.popUp` 才是真的广告下发口。
结论：先抓包看清 URL 和调用时机，再决定拦不拦，别按名字猜。

**9. 国内风控域名被丢进代理，比广告更影响体验。**
`mum.alibabachengdun.com`（杭州橙盾，阿里系风控）和 `cdn.ynuf.aliapp.org`
（阿里 WebUMID / 无痕验证码资源）本次实测全部命中 `FINAL,PROXY` 走了境外节点。
表现是验证码转圈、偶发「网络环境异常」。这类域名必须显式 `DIRECT`，
不能指望 `GEOIP,CN` —— 它们解析出 fake-ip，GEOIP 判不出归属（同坑 4）。

**10. `/api/log` 是日志流，不是文件下载口。**
`http://<手机IP>:1082/api/log` 是 chunked 长连接，连上就从缓冲区重放再追实时；
手机浏览器里开着那个页面时脚本抢不到数据（收到 0 字节）；VPN 断开后端口直接
`Connection refused`；日志里的中文是 GBK→UTF-8 二次编码，不反解码连策略名都对不上。
`tools/fetch_sr_log.py` 把这几个坑都处理了。

## 免责

当前试验版仍需真机验证，具体范围和撤销方式见 `report/alipay-mp-analysis-20261120.md`。
不要按公司归属或 IP 网段猜测广告用途。
