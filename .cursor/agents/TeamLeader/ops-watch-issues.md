# 运维盯岗待优化

给下一任组长改 `ops-engineer` / `listen` 循环用。不是当前 YOLOE 盘面。盘面仍看 [HANDOFF-YOLOE-v1.1.md](HANDOFF-YOLOE-v1.1.md)。

用户 2026-11-18 08:54：把「连接反复失败掉线」记下来，另喊组长优化。

---

## 1 Connection failed repeatedly（2026-11-18）

- **现象**：盯 gd04 gqa generate 的运维子代理在跑了约 **12.5 小时**后结束，状态 `error`，明细 **`Connection failed repeatedly`**。同秒运维挂的 `listen`（终端 `855561`，第七挂）`aborted`，`exit_code=1`。
- **不是**：generate 卡死、房间 `done`、用户叫停。
- **当时盘面**（组长代查）：`generate.py` PID **1118187** 仍在，`--rules-scene gqa --export`；日志 `/tmp/gd04-gqa-generate.log` **describe 97%**（约 98018/101406）；8081 仍 `LISTEN`。用户刚问过剩余时间。
- **ID**
  - 组长：`492d2743-f6e0-4298-bc27-9253d6947baf`（项目 `YOLOE-v1.3`）
  - 掉线运维：`c7e29176-82b0-43b1-933b-4b7ca46dd803`（2026-11-17 20:16 挂上，2026-11-18 08:53 报错结束）
  - 重挂运维：`d8942bdf-b7f1-4532-829c-2768dcad4f9e`
- **做法对照**：运维按手册循环 `listen --id <组长 AgentID>`（单次约 2 小时 `TIMEOUT listen still quiet`），醒来探 PID / 8081 / 日志末行，再挂 `listen`。`TIMEOUT` 是安静结束，应再挂，不算下班。这次是子代理连接失败整条对话断了，循环一起停。
- **建议优化**
  - 长盯（一夜、十几小时）子代理连接失败时，组长侧要能发现并自动续派，不要等用户问「运维咋下班了」。
  - 区分三种退出：`listen` TIMEOUT（再挂）、子代理 `Connection failed`（续派）、generate 收口（交数据工程师 `train_segm`）。
  - 运维进度现在只写票 `todo.md`，用户这条对话看不到；长盯要不要定期回一句进度，由优化组长定。
- **2026-11-18 已改**
  - `room.py` 增加 `watch`：安静打 `CHECK` 不退，约 12 小时打 `TIMEOUT watch` 再挂。
  - 长盯由这条组长对话自己挂 `watch`，运维另盯进程。运维 `Connection failed` 立刻再派，不算下班、不算收口。

---

## 2 listen 只听房间、没核 generate 是否真起来（2026-11-17）

- **现象**：8081 起来之后 `generate.py` 因路径未加引号失败（exit 2），运维只报服务/房间，没核到业务 PID 和日志就绪字。用户问「为什么没检查有没有启动」。
- **已改手册**：`.cursor/agents/ops-engineer.md` 8081→generate 闸（`ss :8081`、`/v1/models`、`generate.py` PID、日志 `rules_scene` 与 vLLM 就绪，缺一交回）。
- **闸仍有效**。长盯掉线已由 `ccd70df8` 在 §1 改完，并提交干净仓 `b9ff46d`。交接见 [HANDOFF-ccd70df8.md](HANDOFF-ccd70df8.md)。

---

## 3 房间回执把盯岗打停，接着新开子代理起不来（2026-11-19）

- **现象**：建筑 v1.5 训到大约第 117 轮，房间一句回执（不抢卡、等两边测完）让 `watch` 退出。运维交回「停听了，训练没完」。组长立刻再派一棒。新子代理状态是 **Couldn't start**。组长只好在这条对话里自己看终端。几分钟里连着停听、再派。
- **不是**：训练卡死，也不是对方干完。
- **已改**
  - `room.py` 的 `watch` 遇到写给自己的留言只打印，不退出。短等 `listen` 仍会退出。`READY` / `ABSENT` 仍退出。
  - 长盯的 `watch` 挂在组长这条对话上。运维只核进程和日志。回执且活还在，不新开运维。
  - 子代理 `Couldn't start`：组长自己核一次，同一轮不要连开。下一轮核对等到下一次 `CHECK`。
