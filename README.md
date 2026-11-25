# Mihon 中文扩展源（国内直连精选）

给 [Mihon](https://mihon.app) / Tachiyomi 用的第三方扩展源。内容取自 keiyoushi 官方仓库，
只保留**在中国大陆网络下实测可直连**的 56 个中文扩展，需要代理才能访问的站点全部剔除。

## 怎么用

在 Mihon 里添加这个地址（设置 → 浏览 → 扩展仓库 → 「+」）：

```
https://gcore.jsdelivr.net/gh/Summerlorn/mihon-cn-extensions@main/index.min.json
```

地址必须完整以 `/index.min.json` 结尾，不要加任何参数。

加完之后：

- 列表里只出现这 56 个扩展，安装、图标、更新全部走 jsDelivr 的 gcore 节点，国内直连无需代理
- 其中 10 个是 18+ 站点，需要在「设置 → 浏览」里打开「显示 NSFW 内容」才会显示
- **请把 keiyoushi 官方源关掉**，否则同一个扩展会出现两份、互相抢更新

### 为什么用 gcore 节点

jsDelivr 的 `fastly` 节点对 `.apk` / `.png` 会返回 301 跳到 `raw.githubusercontent.com`，
而那个域名在国内不可靠，装扩展可能卡住。实测 `gcore.jsdelivr.net` 对索引、APK、图标
一律 200 直出（本机 TTFB 0.8–1.4s），`testingcf.jsdelivr.net` 同样可用但略慢，
两者都可以作为备选。

## 文件结构

```
index.min.json   扩展索引（56 个扩展 / 65 个中文源站，裸数组格式）
repo.json        源名称与签名指纹（keiyoushi 官方签名）
sync.py          跟随上游同步的脚本（由 GitHub Actions 每天调用）
packages.txt     收录哪些扩展（一行一个包名）
domains.txt      哪些站点域名算国内可直连
apk/             扩展安装包（每个包保留当前版本 + 上一个版本）
icon/            56 个对应图标
```

Mihon 会按 `<仓库地址>/apk/<文件名>` 和 `<仓库地址>/icon/<包名>.png` 取文件，
所以这个目录结构不能改。

## 自动同步

`.github/workflows/sync.yml` 每天北京时间 11:23 拉取 keiyoushi 官方索引，
把列入 `packages.txt` 的扩展升到最新版，连同新 APK 一起提交。

注意两点：

- jsDelivr 对 `@main` 有 12 小时缓存，更新后手机上最多延迟 12 小时才能看到新版本
- 每个扩展只保留中文（`zh*`）源；英文等其它语种源会被过滤掉

## 说明

- APK 全部为 keiyoushi 原包，未做任何修改，签名为 `9add655a78e96c4ec7a53ef89dccb557cb5d767489fac5e785d671a5a75d4da2`
- 扩展的版权归各站点与 keiyoushi 原作者所有，此仓库仅做镜像与可达性筛选
- 站点域名和网络状况都会变化，收录与否是 2026-11-22 的实测快照
