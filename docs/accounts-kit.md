# 开号备件（内部工单 §2，2026-09-29；图片节由补丁 5、补丁 6 改写；补丁 8 升 v3.3）

四个平台（B 站／微信公众号／YouTube／X）开号时要上传、要填写的东西都在这里。开通步骤见 `docs/accounts-checklist.md`。

**取件处只有一个：`~/Desktop/pg-accounts-kit/`，按平台分四个子目录。** 上传时从那里拿文件，不从仓里拿。仓里的 `site/assets/brand/` 是留底，取件目录里的图都是从仓里复制的（对应关系见 §2.3、§5）。

本文件只记公开信息。邮箱地址、手机号、恢复码、密码及任何凭证不写进本仓。

## 1 名字

| 项 | 值 | 长度实测 |
|---|---|---|
| 显示名（中文） | 物理AI实验场 | 7 个字符（5 个汉字＋AI）；汉字按 2 计为 12 |
| 显示名（英文） | Physical AI Proving Ground | 26 个字符 |
| handle | physicalaipg | 12 个字符 |

## 2 图片（内部工单、补丁 6 及其修订 2 改写，2026-09-29）

补丁 4 出的三张图已作废，由下面五个语域的图替代。规格见 `docs/brand-spec.md`。

**v3.3（内部工单）**：flat 的 YouTube 横幅与 X 头图改为英主中副——主字 Physical AI Proving Ground，副字「物理AI实验场」，第三行 Simulation first, anchored by real-robot runs（英文简介第二句，去句号）。图形没有动；五张头像与其余四个语域的横幅、头图都没有动。

### 2.1 五个语域

| 语域 | 叫法 | 仓内目录 | 画的是什么 | 用途 |
|---|---|---|---|---|
| flat | 正装 | `site/assets/brand/flat/` | 线框透视网格、一串雾青轨迹点、一枚琥珀圆盘；没有角色 | X、YouTube |
| cute | 第二版 | `site/assets/brand/cute/` | 角色「小M」坐在场上，圆眼 | B 站、微信公众号 |
| cute-pro | 第二版Pro | `site/assets/brand/cute-pro/` | 小M 坐在场上，笑脸、偏头 | 与非 Pro 版按内容情绪选用；不进取件目录 |
| lounge | 第三版 | `site/assets/brand/lounge/` | 小M 侧躺在场上，眼皮半垂 | 不上头像；留作内容配图与周边 |
| lounge-pro | 第三版Pro | `site/assets/brand/lounge-pro/` | 小M 仰躺露肚皮，笑脸 | 与非 Pro 版按内容情绪选用；不进取件目录 |

- 角色名「小M」，项圈铭牌字母 M。
- 新旧两张脸并存，五个语域全部入库备用，没有作废的。cute、lounge 是 v2 包的图；cute-pro、lounge-pro 是 v3 包的图。
- 每个语域三张图，png 与 svg 各一份，共 30 个文件。svg 里的字已转成轮廓。

### 2.2 平台分配

| 平台 | 语域 | 头像 | 横幅／头图 | 取件子目录 |
|---|---|---|---|---|
| X | flat | `avatar-800.png` | `header-x-1500x500.png` | `~/Desktop/pg-accounts-kit/x/` |
| YouTube | flat | `avatar-800.png` | `banner-youtube-2560x1440.png` | `~/Desktop/pg-accounts-kit/youtube/` |
| B 站 | cute | `avatar-800.png` | 无 | `~/Desktop/pg-accounts-kit/bilibili/` |
| 微信公众号 | cute | `avatar-800.png` | 无（公众号没有横幅位） | `~/Desktop/pg-accounts-kit/wechat/` |

cute 的横幅、头图只在仓里，没有放进取件目录。cute-pro、lounge、lounge-pro 三个语域整个不进取件目录。

### 2.3 校验表（五个语域 × 三张图，sha256 全长）

路径相对 `site/assets/brand/`。像素、字节、sha256 都是入库后实测。

| 语域 | 件 | 文件 | 像素 | 字节 | sha256 |
|---|---|---|---|---|---|
| flat | 头像 | `flat/avatar-800.png` | 800×800 | 23967 | `439e797d6d87ca5b141e0b55704ee1c3cf3bba335c84a1bb811bb9aa169d318d` |
| flat | YouTube 横幅（v3.3） | `flat/banner-youtube-2560x1440.png` | 2560×1440 | 85972 | `fc05f14d8c604ba2897115045a28eecdcadd330ea71edef06da9198b409b9bdd` |
| flat | X 头图（v3.3） | `flat/header-x-1500x500.png` | 1500×500 | 48388 | `5c4d6492e2055187889b3708c83a10835d9689ddf335123130e4dc44074c2fe9` |
| cute | 头像 | `cute/avatar-800.png` | 800×800 | 55180 | `81b865b77b2fa8c2e17f0203867f0fc41d1a88131782714f8e67907d2fdc5862` |
| cute | YouTube 横幅 | `cute/banner-youtube-2560x1440.png` | 2560×1440 | 102685 | `0d896e6c33a440c19b2277f852e870f8780866aa605ddf2e89df45cb3788dbea` |
| cute | X 头图 | `cute/header-x-1500x500.png` | 1500×500 | 58822 | `f26d85f7ab674467a2e157993df0d2f68e22b58995e4ca184ab82e8bb17feff1` |
| cute-pro | 头像 | `cute-pro/avatar-800.png` | 800×800 | 60383 | `3c69c7b3e2e3b3d28622146dd6f05f61e441abd53311a54aa7c81f822954f03e` |
| cute-pro | YouTube 横幅 | `cute-pro/banner-youtube-2560x1440.png` | 2560×1440 | 104857 | `c5e313fc6dbe0e542315bc2b17fc4b482ff2e84a8ed6b60f88bb2280dfae9029` |
| cute-pro | X 头图 | `cute-pro/header-x-1500x500.png` | 1500×500 | 59729 | `834465a09846437c094fbbe4db9dc3bd297e83cc6a7c689457de67bcd04d339e` |
| lounge | 头像 | `lounge/avatar-800.png` | 800×800 | 62208 | `b9946fa51e7ff0d9ebccc0031071bb4940a71fdfb20b2c5c29f6c0f602c1ff67` |
| lounge | YouTube 横幅 | `lounge/banner-youtube-2560x1440.png` | 2560×1440 | 107077 | `60b26513a7bc0effa82306e683387c1f91e83e1b797fd5fa19086b393cd8f9e1` |
| lounge | X 头图 | `lounge/header-x-1500x500.png` | 1500×500 | 60919 | `85895f03e17549557942bac79036307f2db99446d6b838b651626b831394b135` |
| lounge-pro | 头像 | `lounge-pro/avatar-800.png` | 800×800 | 72952 | `ddd1c9090f4dbf9fe71ab07921dd6b9e528d247eac8214874c3c5a239c8969bc` |
| lounge-pro | YouTube 横幅 | `lounge-pro/banner-youtube-2560x1440.png` | 2560×1440 | 113531 | `62c960e50a4f9f2230f411cdaca0fe7be22eddaeb37ce182eddb34dd07f3833b` |
| lounge-pro | X 头图 | `lounge-pro/header-x-1500x500.png` | 1500×500 | 65747 | `8fad369bf640f6bea9db8db12f6c434dfe168528a328cd45bdef840b30c8c866` |

取件目录里的图是从仓里复制的：四张头像与两张带 `-v3.3` 的横幅，sha256 与上表对应行相同；两张不带后缀的旧横幅（v3.2，中主英副）与 §2.6 作废件相同。

### 2.4 字体

Noto CJK／站酷快乐体／Fredoka，均 OFL。站酷快乐体与 Fredoka 的字体文件和许可证在 `tools/brand/fonts/`；Noto CJK 没有随包送来，不在仓里。

### 2.5 再生成

再生成用 `tools/brand/regen.sh`，它装好依赖、备好字体后原样执行 `tools/brand/build.py`：

```bash
bash tools/brand/regen.sh <输出目录>   # 出五语域，png 与 svg 共 30 个文件
bash tools/brand/regen.sh --check      # 出到临时目录，与 site/assets/brand/ 逐个比 sha256
```

- 前提：python3、curl，系统装有 cairo（macOS：`brew install cairo`）。
- 依赖装在 `~/.cache/pg-brand/` 下的虚拟环境里，版本固定为 fonttools 4.66.0、uharfbuzz 0.56.2、cairosvg 2.9.1、pillow 12.3.0。
- 字体：Noto Serif CJK 2.002 的 Black、SemiBold、Regular 三个 ttc，首次运行时下载到同一缓存目录并核 sha256，不入仓。
- `python3 tools/brand/build.py <输出目录>` 在这台 Mac 上直接跑会失败：缺依赖，且 `brand.py` 里 Noto 目录写的是 Linux 路径。`build.py`、`brand.py` 没有改，`regen.sh` 在导入后改指字体目录。
- `--check` 还核开号目录（缺省 `~/Desktop/pg-accounts-kit/`，环境变量 `KIT_DIR` 可改）里 `names-and-bios.txt`「图片」段列的每个文件是否真实存在（内部工单 §3）；目录不存在时跳过并提示，不算失败。
- 2026-09-29 实测：空缓存起跑，`--check` 退出码 0，30 个文件与入库件逐个相同。把字体换成 2.003 版，`--check` 退出码 1，报 flat 的 YouTube 横幅与 X 头图（png、svg 共 4 个文件）不同。2.001 版同样是这 4 个不同（三语域那一版脚本上试的）。

### 2.6 作废件（只移不删）

| 目录 | 内容 | 作废于 |
|---|---|---|
| `site/assets/brand/_retired/2026-09-29/` | 补丁 4 的三张 png（方框折线标识） | 补丁 5 |
| `site/assets/brand/_retired/2026-09-29-v3.2/flat/` | v3.2 的 flat YouTube 横幅与 X 头图，png 与 svg 共 4 个（中主英副；`e7397075…`、`f255e379…`）；把 `build.py` 的 `PRIMARY` 改回 `"zh"` 可逐字节重出 | 补丁 8 |

补丁 6 曾把 v2 的 cute、lounge 移进 `_retired/2026-09-29-v2/`（pg `3504481`）；修订 2 改判不作废，已移回 `cute/`、`lounge/`，那个目录不再存在。

`tools/make_brand.py` 是补丁 4 的出图脚本，出的是已作废的那三张图；脚本还在仓里，没有动。

### 2.7 没做的事

- 标识和角色都没有拿去商标库或图片搜索里比对过。这一项另令办，排在 10-29 公开之前。
- 40 px 圆裁核对：CC 没有自己做。随包送来的六张预览图（每张含圆裁小样）已入 `docs/brand-previews/`，CSO 以此关闭这一项（内部工单）。
- v3.3 两张横幅的三层预览在 `docs/brand-previews/preview-v3.3-*.png`：YouTube 电视层（整图缩到 1280×720）、桌面层（中央 2560×423）、手机层（中央 1546×423），另有一张 X 头图叠头像的示意；都是从成品图裁出来的，平台上的实际显示没有核过。
- X 没有公布安全区，头图左下头像区（约 x<380 且 y>320）是估的。上传后以预览为准，头像压到内容就告诉 CC 重出。

## 3 简介

| 版本 | 文字 | 长度实测 | 上限 |
|---|---|---|---|
| 中文 | 公开、可复现的物理AI评测。仿真为主，真机为锚。首期榜单 2026-10-29 发布。 | 43 个字符（含标点、数字、空格） | ≤60 |
| 英文 | Open, reproducible physical-AI evaluation. Simulation first, anchored by real-robot runs. First leaderboard: 2026-10-29. | 120 个字符 | ≤150 |

- 两版都只陈述事实，没有「权威／官方／第一」一类的词，没有使命句。
- 公众号「功能介绍」的字数下限，CC 记得是 4 个字，没有去官方页面核；中文版 43 个字符，离这个数很远。以注册页提示为准。
- 「首期榜单 2026-10-29 发布」在 10-29 之后就过时了，到时要换一句。

## 4 各平台用哪几件

| 平台 | 显示名 | 图片 | 简介 |
|---|---|---|---|
| B 站 | 物理AI实验场 | 见 §2.2 | 中文 |
| 微信公众号 | 物理AI实验场 | 见 §2.2 | 中文，填「功能介绍」 |
| YouTube | Physical AI Proving Ground | 见 §2.2 | 英文 |
| X | Physical AI Proving Ground | 见 §2.2 | 英文 |

各平台对名字长度、图片大小的限制，CC 没有逐个去官方页面核。上传页提示不符时，把提示原文告诉 CC。

## 5 取件目录清单

`~/Desktop/pg-accounts-kit/` 里共 10 个文件：上传用带 `-v3.3` 的横幅，不带后缀的两张是已上线的旧横幅，留着没有删。

| 子目录 | 文件 |
|---|---|
| `x/` | `avatar-800.png`、`header-x-1500x500-v3.3.png`、`header-x-1500x500.png`（flat） |
| `youtube/` | `avatar-800.png`、`banner-youtube-2560x1440-v3.3.png`、`banner-youtube-2560x1440.png`（flat） |
| `bilibili/` | `avatar-800.png`（cute） |
| `wechat/` | `avatar-800.png`（cute） |
| 根目录 | `names-and-bios.txt`（显示名、handle、两版简介，供复制粘贴） |

`names-and-bios.txt` 是补丁 4 写的；它末尾「图片」一段补丁 9 按开号目录现状重写成六行（`子目录/文件名` 开头，文件名以 `ls` 为准），`x/`、`youtube/` 只列头像与带 `-v3.3` 的横幅，`bilibili/`、`wechat/` 列第二版圆眼头像。防漂移：`regen.sh --check` 读这一段，每个文件名须在对应子目录真实存在，缺一个即退出码 1（§2.5）。图片分配仍以本文件 §2.2 为准。

## 6 公众号搜一搜二维码（内部工单，2026-09-29）

主理人从公众号后台下载的两张，原件是 BMP 数据、文件名带 `.png` 后缀；转成 PNG 后入库，像素与原件逐个相同。用在实验场站点页脚（10-29），不上人牌页。

| 文件（相对 `site/assets/brand/accounts/wechat/`） | 像素 | 字节 | sha256 | 原件 sha256 |
|---|---|---|---|---|
| `qr-search-green-1816x624.png`（绿底） | 1816×624 | 129725 | `e01d23c8a47cf7838a098cd5e9a8a52fbc4ebed4a4788227caf664e8fa9fe531` | `1563ac5145615ffcca3d469004fecb7ba75f91862c3183e66c6fdc8af6c8a780` |
| `qr-search-white-1816x624.png`（白底） | 1816×624 | 126143 | `e0db44fb53d7a9f919369306d6d47667e948b99a3eaea9dc54bd29f2f59750ae` | `17f859a892564c6b26b9017ea092a2c065fecfb478289f7678e1bf05e5d219b6` |

二维码没有扫过，扫出来指向哪里 CC 没有核。
