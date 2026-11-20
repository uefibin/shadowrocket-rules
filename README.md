# Shadowrocket 规则集

> 2026-11-20 当前开屏排查：优先看 [支付宝分析报告](alipay-analysis-2026-11-20.md)。
> 新完整试验配置为 `AdBlock_SR.alipay.conf`，仅合并规则用 `fragment-alipay-current.conf`。
> 哈啰 `adx.ssp.show` 在日志中已被拒绝，但用户反馈 6 秒开屏仍出现，
> 因此试验版增加 `homepage.recommend.popUp` 候选拦截，尚待真机验证。
> `adblock-alipay-captured.conf` 的旧 IP 段拒绝已撤回；不要恢复 203.209.* 拦截。
> 下方旧“实测”描述不代表这次已验证全部结论，以当前报告的证据范围为准。

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
| `AdBlock_SR.slim.conf` | **主用**。完整配置，含分流策略组 + 去广告段 |
| `AdBlock_SR.conf` | 上游原版（懒人配置），留作对比参考 |
| `lint_sr.py` | 配置校验器，改完先跑它 |
| `adblock-alipay-captured.conf` | 支付宝小程序抓包结论片段，可单独贴 |
| `adblock-wx-alipay.conf` | 微信/支付宝通用广告域名片段 |
| `adblock.list` | 纯域名清单，适合并入已有配置 |
| `verify_rules.py` | 早期规则引擎，可模拟某域名命中哪条（`lint_sr.py` 更全面，保留作互补） |

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

用 `fragment-alipay-hellobike.conf`：整段复制，粘到你现有配置 `[Rule]` 的**最上面**。
撤销就整段删掉。

改动范围最小，适合只想加几条规则、不想动其余部分的情况。

顺序不能改，原因见下。

## 维护

```bash
python lint_sr.py AdBlock_SR.slim.conf            # 语法、策略名、顺序、重复
python lint_sr.py AdBlock_SR.slim.conf --online   # 另加远程规则集可达性探测
python lint_sr.py 新.conf --compare 旧.conf        # 两版量化对比
```

`--online` 走系统代理；需要时设 `HTTP_PROXY` 环境变量。

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
原文件规则写 `YOUTUBE`、组定义 `YouTube`，靠 SR 大小写不敏感才没出错。不该依赖这种运气。

## 免责

当前试验版仍需真机验证，具体范围和撤销方式见分析报告。不要按公司归属或 IP 网段猜测广告用途。
