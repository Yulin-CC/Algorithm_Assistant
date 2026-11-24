# 组长房间协议

`room.py` 的用法与监听退出语义。常驻规则只在需要时指过来，日常不必逐条复述。

房间不是新工种。工程师不进这个房间；它们的心跳只用派工里的组长 AgentID。

- [1 登记](#1-登记)
- [2 等另一个项目](#2-等另一个项目)
- [3 长盯的三种退出](#3-长盯的三种退出)
- [4 什么时候不算干完](#4-什么时候不算干完)
- [5 子代理起不来怎么办](#5-子代理起不来怎么办)

---

## 1 登记

```bash
py -3 .cursor/agents/TeamLeader/room.py join --id <AgentID> --project <项目>
py -3 .cursor/agents/TeamLeader/room.py read
py -3 .cursor/agents/TeamLeader/room.py say --id <AgentID> --to <对方> --text "..."
py -3 .cursor/agents/TeamLeader/room.py done --project <项目>
py -3 .cursor/agents/TeamLeader/room.py leave
```

- 接到活才 `join`。纯问答不登记。
- AgentID 只用开场注入的那一个。没注入就先不登记，不另编。
- 自己干完：先 `done --project` 再 `leave`。活没干完只 `leave`。
- 每轮先 `read`。同一服务器、GPU 或数据根已有人 `working`，先 `say` 再动手。

## 2 等另一个项目

```bash
py -3 .cursor/agents/TeamLeader/room.py join --id <AgentID> --status waiting --wait-for <项目>
py -3 .cursor/agents/TeamLeader/room.py wait --project <项目>
```

- 只认**本次等待开始之后**的 `done`，见到才改为 `working` 并开工。
- 心跳超时、关对话、没有 `done` 的 `leave`，都不开工。登记保持 `waiting`，并告诉用户。
- 名单上暂时没有对方，也不算干完。
- 单次等待约 2 小时，到点说明还在等。用户说继续就再跑 `wait`；已经报过的那次退出不会再次挡下这次等待。

## 3 长盯的三种退出

`watch --id <AgentID>` 和 `listen` 都会打出事件名，但退出规则不同。

| 事件 | `watch`（组长自己挂） | `listen`（子代理里挂） |
| --- | --- | --- |
| `CHECK`（安静） | 不退，继续挂 | 退回，探完再挂 |
| `SAY`（有人说话） | **不退**，读完回房间即可 | **会退**，活没完就在原来那条子代理里再挂 |
| `READY` / `ABSENT` | 退 | 退 |
| `TIMEOUT` | 约 12 小时打 `TIMEOUT watch`，再挂同一条 | 约 2 小时打 `TIMEOUT`，探完再挂 |

要点：

- `watch` 上打出 `SAY`，进程不退。**读完回房间即可**，不要停掉 `watch`，也不要为这句回执再派运维。
- `READY` 才退，组长再读再回。
- `listen` 上的 `SAY` 会退。训练没完，就在原来那条子代理里再挂，**不要为此新开一棒**。
- 不要把唯一一条 `listen` 只挂在运维子代理上。长活期间组长这条对话自己挂 `watch`。
- 不另编 id。
- 对话关掉循环会停，这仍然算掉线。长活开始时用人话提一句「这条对话先开着」。

## 4 什么时候不算干完

- 心跳超时，不算对方干完。
- `stale` 或没有 `done` 的 `leave`，不算干完。
- `listen` 打出 `READY`，或对方 `done`，只说明那一棒房间结束，**不算服务就绪**。
- 房间一句回执、活还在，不算交回，不要结束本棒等组长再派。

反过来，运维的 `CHECK` 或安静超时叫醒后，还要看派工点名的进程、端口和日志末行。只交房间消息、或只说「还在跑」，不算盯完。没卡也要带回 PID 或日志末行。

## 5 子代理起不来怎么办

| 现象 | 怎么办 |
| --- | --- |
| 运维子代理断开或 `Couldn't start` | 再派一次；再起不来，本条对话才代查一次进程和日志。**同一轮不要连开**，下一轮核对等到下一次 `CHECK` |
| `Connection failed`，或对话关掉 | 再派一次；再起不来就同样自己核，不要连开 |
| 组长挂着 `watch` 且运维还在跑 | 不要自己探进程，也不要再派 |

这些都不是收口。`CHECK` / `TIMEOUT` / `Connection failed` 都不代表活已经干完或可以下班。
