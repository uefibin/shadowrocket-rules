# Shadowrocket 规则集

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

### 方式一：整个配置订阅（会替换当前配置）

Shadowrocket › 配置 › 添加 › 输入 URL：

```
https://raw.githubusercontent.com/uefibin/shadowrocket-rules/main/AdBlock_SR.slim.conf
```

注意这是**完整配置**，订阅后节点组会从你的订阅里按关键词自动筛选（香港/台湾/日本/新加坡/韩国/美国）。
如果你已经有一份调好的配置，别用这个方式，用方式二。

### 方式二：只取去广告段（推荐）

打开 `AdBlock_SR.slim.conf`，把 `[Rule]` 下面第 0～4 段（白名单 → 广告 → 腾讯 → SDK → 可选）
整段复制，粘到你现有配置的 `[Rule]` **最上面**。撤销就整段删掉。

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

**3. 小程序广告是裸 IP 直连，没有域名可拦。**
小程序跑不了原生广告 SDK，广告是 H5 组件，素材由业务接口直连下发。
支付宝小程序的广告素材打在 `203.209.230/243/250.0/24`，归属「杭州阿里巴巴广告有限公司」。
只能拦素材，拦不住广告位 —— 预期效果是广告图文/视频加载不出来（灰块），位置还在。

**4. 微信拦不了 HTTPS 层。**
微信走 MMTLS、支付宝走 mPaaS，都有证书固定。对它们开 HTTPS 解密 =
支付失败 / 登录异常 / 风控提示。只能在域名和 IP 层 REJECT，效果相当于弱网，风控基本无感。

**5. 策略名大小写别赌。**
原文件规则写 `YOUTUBE`、组定义 `YouTube`，靠 SR 大小写不敏感才没出错。不该依赖这种运气。

## 免责

规则按「能拦就拦」的思路写，没有做灰度验证。`203.209.x` 三段和淘宝/支付宝的图片 CDN
在同一批机房，若发现**商品图、头像变灰块**，先把那一段注释掉再逐条加回。
