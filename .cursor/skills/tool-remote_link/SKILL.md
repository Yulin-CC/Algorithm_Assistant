---
name: tool-remote-link
description: >-
  Operate local Windows against remote Ubuntu via SSH key / BatchMode.
  Default host is whatever workarea/link.md records for this checkout, currently
  ubuntu@<HOST>. Directory map, vLLM/SAM URLs and start scripts live in
  workarea/link.md — read that first for server ops. A new
  environment runs init, writes workarea/link.md, then updates this skill's Server IDs. Use when
  the user mentions <HOST>, 操作服务器, vLLM,
  上传数据, local↔remote transfer, or another SSH host.
---

# Remote `<HOST>`

本机 ↔ 远端 Ubuntu 的操作策略。主机以 `workarea/link.md` 为准；新环境先走初始化，把主机写进 `workarea/link.md`，再改下面的 Server IDs。当前这份填写是 `ubuntu@<HOST>`。用户指定**其它主机**做上传/下载时，先走 [New server] 做密钥校验并登记 Server ID。后续可追加路径约定；当前先固化**数据传输**。

## Server IDs

已登记、可用密钥直连的主机。默认只用表中第一行。`workarea/link.md` 该行确认列还是待确认时，本表不算用户已经点头。初始化里用户点头之后再改本表。

| ID | SSH | 备注 |
| --- | --- | --- |
| `<HOST>` | `ubuntu@<HOST>` | 默认 |
| `<HOST>` | `caiyulin@<HOST>` | 4x3090。驱动 550.90 / CUDA 12.4。不是默认 |

## New server

用户指定的上传/下载目标**不是** `ubuntu@<HOST>` 时：**先测密钥连通，再传文件**。未通过不得 `scp` / 管道上传。

**(1)** 探测（`BatchMode=yes`，禁止交互要密码）：

```bash
ssh -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new <user@host> "echo OK && hostname && whoami"
```

- 成功（远端回 `OK`）→ 把该主机追加进上方 **Server IDs**（`ID` = 主机地址或用户给的短名，`SSH` = `user@host`），再按后文传输（把示例里的 `ubuntu@<HOST>` 换成新 ID）。
- 失败 → **停止传输**，进入 **(2)**，不得改用密码登录代传。

**(2)** 无密钥：引导用户做密钥匹配。Agent **不得**索要/代输密码，**不得**读取或回显私钥。

向用户说明：本机公钥尚未授权到该主机，请在**本机终端自行**执行。

确认公钥（有则跳过生成）：

```powershell
Get-ChildItem $env:USERPROFILE\.ssh\id_ed25519.pub, $env:USERPROFILE\.ssh\id_rsa.pub
```

没有则生成：

```powershell
ssh-keygen -t ed25519 -N '""' -f $env:USERPROFILE\.ssh\id_ed25519
```

把公钥写入远端 `authorized_keys`（可交互一次密码；**Agent 不执行**）：

```powershell
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh <user@host> "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

**(3)** 用户回复「已配好」后，Agent **重新跑 (1)**。仍失败则区分：网络不通 / `Permission denied`（公钥未装上）/ 用户名不对。未通过不得继续、不得登记 ID。

- **注意**：全程 `BatchMode=yes`。对话中不要出现私钥内容。用户若把私钥或密码贴进聊天，不要写入文件或回显，提醒其作废并重配。

## Connection

```bash
ssh -o BatchMode=yes -o ConnectTimeout=15 ubuntu@<HOST> "<cmd>"
```

长传加保活：

```text
-o ServerAliveInterval=30 -o ServerAliveCountMax=120
```

- 默认主机已配置密钥，**不要**交互输密码
- 非默认主机先走 [New server]，通过后再把上面的 `ubuntu@<HOST>` 换成新 ID
- Windows PowerShell 下远程命令用单引号包住整段。不要在双引号里写 `\"`，竖线会被拆开。避免 `$(...)` 被本地展开

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=15 ubuntu@<HOST> 'echo OK && hostname && whoami'
```

## Disk rule（强制）

本机 D: 经常空间紧。原则：

1. **一次只处理一个数据集**
2. 确认完整后立刻删临时包（本地 + 远端）
3. 大体量（本地放不下整包）→ 用**方案 B 流式**，禁止先打满盘的本地大包

**禁止**：未经用户明确同意，移动/删除/改写 `/path/to/PATH`（团队备份）。

## Upload strategies

### A. 小/中包（本地放得下）

适合：源数据 + 压缩包峰值 < 本地剩余空间（留余量）。

1. 本地压缩（JPEG 为主时 gzip 几乎不缩，仍可用 `tar.gz` 便于管理）  
   ```bash
   tar -czf _upload_tmp/<EnglishName>.tar.gz -C "<中文源目录>" images jsons train.txt
   ```
   直接打成英文名内容，避免中文路径在 tar/scp 上踩坑。
2. `scp` 到远端目标父目录
3. 远端：`mkdir -p <EnglishName> && tar -xzf <EnglishName>.tar.gz -C <EnglishName>`
4. **核对**（见下）通过后：删远端 zip + 本地 zip
5. 再下一个

### B. 流式（本地放不下整包）— 默认用于百 GB 级

本地**不落**大包，边打包边经 SSH 解压：

```bash
# Windows cmd 管道示例（JPEG 已压缩：用 -cf 即可，别盲目 -czf）
tar -cf - -C "<中文源目录>" images jsons train.txt ^
| ssh -o BatchMode=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=120 ^
    ubuntu@<HOST> "mkdir -p '<远端英文目录>' && tar -xf - -C '<远端英文目录>'"
```

PowerShell 注意：二进制管道优先走 `cmd /c "tar ... | ssh ..."`，减少 PS 管道捣乱。

传完后同样做数量/stem 核对。无本地/远端大 zip 可删。

监控建议：每几分钟查远端 `images`/`jsons` 计数；进程应能看到本地 `tar.exe` + 对应 `ssh.exe`。

## Verify（上传完成标准）

远端目标目录内：

- `images` 文件数 == 本地
- `jsons` 中 `.json` 数 == 本地（忽略 cache）
- stem 一一对应：`missing_json == 0` 且 `extra_json == 0`
- 若有 `train.txt`，确认存在

Python 核对示例：

```python
from pathlib import Path
base = Path("/path/to/EnglishName")
imgs = {p.stem for p in (base/"images").iterdir() if p.is_file()}
js = {p.stem for p in (base/"jsons").iterdir() if p.is_file() and p.suffix == ".json"}
print(len(imgs), len(js), len(imgs-js), len(js-imgs))
```

## Naming（当前约定）

中文目录 → 英文目录（与 `GEOAI-<Prefix>-` 或用户指定一致）。已知安防示例：

| 中文 | 英文 |
|------|------|
| 5-焚烧痕迹 | `5-BurnTrace` |
| 7-人员_船只_车辆 | `7-PersonShipVehicle` |
| 10-烟火 | `10-FireSmoke`（用户指定，非 Firework） |
| 11-工程车 | `11-ConstructionVehicle` |

已有远端：`1-Car` … `9-HeighTrestrictionBar` 等，新增时对齐风格。

## Known roots（草稿，可后续扩展）

本机草稿。没写进 `workarea/link.md`、或确认列还是待确认的，不要沿用到别的机器。

| 角色 | 路径 |
|------|------|
| SSH | 见 [Server IDs]；默认 `ubuntu@<HOST>` |
| 远端安防 | `/path/to/home/0-data/2-DroneObject/SmartSecurity` |
| 远端水务 | `/path/to/home/0-data/2-DroneObject/SmartWaterarea` |
| 本地安防 train | `/path/to/data\2-DroneObject\toclean\YOLO-base\智慧安防\train-训练集` |
| 本地水务 train | `/path/to/data\2-DroneObject\toclean\YOLO-base\智慧水务\train-训练集` |
| 本地临时包 | `/path/to/data\2-DroneObject\toclean\YOLO-base\_upload_tmp\` |

路径映射细则、更多业务策略 → 以后再往本 skill 追加章节即可。

## Checklist（每个数据集）

```
- [ ] 选 A 或 B（看本地剩余空间）
- [ ] 远端父目录空间足够
- [ ] 传/解到英文目录名
- [ ] images/jsons/stem 核对通过
- [ ] 删临时包（若有）
- [ ] 更新项目 TODO（若有）后再做下一个
```
