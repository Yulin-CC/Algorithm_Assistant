"""
# @Author: Yullin
# @Date: 2026-11-17
# @Description: 组长房间 hook。开场注入 AgentID，结束时退出名单且不写 done
"""

import json
import os
import subprocess
import sys


def room_script():
    agents_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(agents_dir, "TeamLeader", "room.py")


def emit(text):
    json.dump({"additional_context": text}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def is_session_end(payload):
    if payload.get("hook_event_name") == "sessionEnd":
        return True
    return "duration_ms" in payload and "reason" in payload


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    session_id = str(payload.get("session_id") or payload.get("conversation_id") or "").strip()
    if is_session_end(payload):
        if session_id:
            subprocess.run(
                [sys.executable, room_script(), "leave", "--id", session_id, "--reason", "sessionEnd"],
                check=False,
            )
        return
    if session_id:
        emit(
            f"组长房间：你的 AgentID 是 {session_id}。"
            "登记、等待、标记干完都用 py -3 .cursor/agents/TeamLeader/room.py，"
            "--id 必须用这个 id。没看到本句就先不登记，不要另编 id。"
        )
        return
    emit("组长房间：这次没有注入 AgentID。本轮先不登记，不要另编 id。")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        main()
    except Exception:
        emit("组长房间：hook 失败，本轮先不登记。")
        sys.exit(0)
