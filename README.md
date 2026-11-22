# Mihon 中文扩展源（国内直连精选）

给 [Mihon](https://mihon.app) / Tachiyomi 用的第三方扩展源。内容取自 keiyoushi 官方仓库，
但只保留**在中国大陆网络下实测可直连**的 56 个中文扩展（63 个源站），需要代理才能访问的站点全部剔除。

## 怎么用

在 Mihon 里添加这个地址（设置 → 浏览 → 扩展仓库 → 「+」）：

```
https://fastly.jsdelivr.net/gh/Summerlorn/mihon-cn-extensions@main/index.min.json
```

地址必须完整以 `/index.min.json` 结尾，不要加任何参数。

加完之后：

- 列表里只出现这 56 个扩展，安装、图标、更新全部走 jsDelivr 的 fastly 节点，国内直连无需代理
- 其中 10 个是 18+ 站点，需要在「设置 → 浏览」里打开「显示 NSFW 内容」才会显示
- **请把 keiyoushi 官方源关掉**，否则同一个扩展会出现两份、互相抢更新

## 文件结构

```
index.min.json   扩展索引（56 个扩展，裸数组格式）
repo.json        源名称与签名指纹（keiyoushi 官方签名）
apk/             56 个官方签名的扩展安装包
icon/            56 个对应图标
```

Mihon 会按 `<仓库地址>/apk/<文件名>` 和 `<仓库地址>/icon/<包名>.png` 取文件，
所以这个目录结构不能改。

## 说明

- APK 全部为 keiyoushi 原包，未做任何修改，签名为 `9add655a78e96c4ec7a53ef89dccb557cb5d767489fac5e785d671a5a75d4da2`
- 扩展的版权归各站点与 keiyoushi 原作者所有，此仓库仅做镜像与可达性筛选
- 站点域名和我这里的网络状况都会变化，这份清单是某一时点的快照
- jsDelivr 有约 7 天缓存，官方扩展更新后本仓库不会自动跟随
