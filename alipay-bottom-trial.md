# 哈啰底部商品推广对照试验

用户反馈 `AdBlock_SR.alipay-diagnostic.conf` 测试中 6 秒开屏未再出现，首页底部仍显示三列电商商品推广。该结果暂未证明开屏消失是某条规则造成的，保留当前诊断配置作为基线。

2026-11-20 重新取得日志：16:28:25 起，至少记录至 16:29:30。三轮首页加载均查询 `homepage.combinations.module` 与 `homepage.coupon.mall.module`，均由 hellobike.com DIRECT 放行。render 已成功解密，只观察到 `/p/yuyan/seaViewConfig_livePlayerConfig/zh_CN.json`，没有证据将它判为商品推广。

日志没有 HTTP 响应体，不能确认商品组件的字段来源。因此这次仅对 `homepage.combinations.module` 做单变量拒绝试验，而不是宣称它已被证明是广告专用接口。

## 手机使用

1. 在 Shadowrocket「配置」添加远程配置：

   ```text
   https://raw.githubusercontent.com/uefibin/shadowrocket-rules/main/AdBlock_SR.alipay-bottom-trial.conf
   ```

2. 选中该配置，确认 HTTPS 解密开关与已安装并信任的 CA，解密主机包含 `api.hellobike.com`、`render.alipay.com`。新文件不含 CA 私钥；导入后请检查证书是否与已信任的 CA 匹配。
3. 全局路由使用「配置」，重连后从后台完全退出支付宝，再打开哈啰并滚动到商品栏。
4. 对比三列商品推广是否消失，同时检查卡券商城、功能入口、底部导航、定位与订单查询。

对照版只新增一条 `homepage.combinations.module` 的 URL-REGEX 拒绝，可能同时影响其他首页组合卡片。没有新增卡券商城、整个首页配置或导航接口的拒绝。

如果商品栏仍在或其他卡片异常，切回 `AdBlock_SR.alipay-diagnostic.conf` 即可撤销新增项。先确认日志中该接口命中 REJECT，再根据界面结果决定保留或撤回，不能从接口名称直接认定广告归属。

原始日志 `capture-bottom-log.txt`、`capture-bottom-live-log.txt` 均被 Git 忽略，不上传。此次不改动工作区中其他来源的新片段、工具或 README。
