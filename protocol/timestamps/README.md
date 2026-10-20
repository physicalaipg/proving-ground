# protocol/timestamps · 预注册锚点的外部时间戳（OpenTimestamps）

> 依据：裁定 2026-10-10-02（内部工单，2026-10-10，主理人拍板）。本目录在 `tools/prereg_check.sh` 监视表之外；**监视件不动**。

## 口径（公开文案照此）
- OTS 凭证只证明「内容不晚于凭证所载区块时间已存在」。`protocol-v0-prereg` 的 2026-09-25 为 git 自报日期，第三方时间证据自本次盖章起算。
- 可写：「规则于〈区块日期〉前已外部锁定，早于 v1 正式批」。不得写：「9 月预注册已获第三方证明」。

## 文件
| 文件 | 内容 | 产出命令 |
|---|---|---|
| `protocol-v0-prereg.txt` | [a] tag 对象与所指提交 hash；[b] prereg_check 监视清单 25 件逐文件 tag 内内容 sha256（shasum 原生行格式，按路径排序）；[c] git／ots 版本与命令 | `bash protocol/timestamps/gen_list.sh`（仓根） |
| `protocol-v0-prereg.txt.ots` | 上述文件的 OpenTimestamps 凭证（初为 pending，满 12 小时后 `ots upgrade protocol/timestamps/protocol-v0-prereg.txt.ots` 补齐比特币区块证明） | `ots stamp protocol/timestamps/protocol-v0-prereg.txt` |

## 核验
- `ots info protocol/timestamps/protocol-v0-prereg.txt.ots`（看凭证所载 calendar／区块）；`ots verify protocol/timestamps/protocol-v0-prereg.txt.ots`（upgrade 后）。
- 盖章结果（2026-10-11 00:16Z upgrade，内部工单 交接条下一步①）：凭证含 3 条比特币区块证明，区块 970739／970754／970794，最早区块时间 2026-10-10 07:25:40Z；本机无比特币节点，`ots --no-bitcoin verify` 打印三区块 merkleroot，已逐条与 blockstream.info 公开区块数据比对一致。公开文案区块日期取 2026-10-10。
- 复算 [b] 任一行：`git show protocol-v0-prereg:<path> | shasum -a 256`。

## 常设
此后预注册类 tag（含 `protocol-v0-real-prereg`、日后若重打的 v1 tag）与正式批结果清单，一入库即同法盖章；盖章满 12 小时后 `ots upgrade` 补齐。租约期内无权写本目录的会话所产生的（如会话二打的 tag），连同本次 upgrade，于 (a) 验收后由 pg 唯一写会话办。
