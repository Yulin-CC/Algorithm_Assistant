"""
# @Author: Yullin
# @Date: 2026-11-17
# @Description: 组长房间。按项目登记在岗、留言、标记干完，并边续心跳边听写给自己的留言。watch 遇到留言只打印，不退出
# @Command: py -3 .cursor/agents/TeamLeader/room.py listen --id <AgentID>
# @Command: py -3 .cursor/agents/TeamLeader/room.py watch --id <AgentID>
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta


#-------------#
# 路径与时限
#-------------#
ROOT = os.environ.get("TEAM_ROOM_DIR") or os.path.dirname(os.path.abspath(__file__))
ONLINE = os.path.join(ROOT, "online.json")
ROOM = os.path.join(ROOT, "room.md")
LOCK = os.path.join(ROOT, ".room.lock")
STALE = timedelta(minutes=45)
KEEP = 200
WAIT_MAX = 2 * 60 * 60
WATCH_MAX = 12 * 60 * 60
POLL = 20
BEAT_EVERY = 20 * 60


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_time(text):
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


def project_key(name):
    return (name or "").strip().casefold()


def split_resources(text):
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


#-------------#
# 文件锁与读写
#-------------#
class RoomLock:

    def __enter__(self):
        os.makedirs(ROOT, exist_ok=True)
        deadline = time.time() + 10
        while True:
            try:
                self.fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(LOCK) > 30:
                        os.remove(LOCK)
                        continue
                except OSError:
                    pass
                if time.time() > deadline:
                    raise SystemExit("room lock busy")
                time.sleep(0.05)

    def __exit__(self, exc_type, exc, tb):
        os.close(self.fd)
        try:
            os.remove(LOCK)
        except OSError:
            pass
        return False


def load_leaders():
    if not os.path.isfile(ONLINE):
        return []
    try:
        with open(ONLINE, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    leaders = data.get("leaders") if isinstance(data, dict) else None
    return leaders if isinstance(leaders, list) else []


def save_leaders(leaders):
    tmp = ONLINE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump({"leaders": leaders}, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(tmp, ONLINE)


def load_lines():
    if not os.path.isfile(ROOM):
        return []
    with open(ROOM, encoding="utf-8") as handle:
        return [line.rstrip("\n") for line in handle if line.strip()]


def save_lines(lines):
    lines = lines[-KEEP:]
    with open(ROOM, "w", encoding="utf-8") as handle:
        if lines:
            handle.write("\n".join(lines) + "\n")


def append_event(lines, project, agent_id, kind, text):
    text = " ".join((text or "").split())
    lines.append(f"{now_text()} | {project or '-'} | {agent_id or '-'} | {kind} | {text}")
    return lines


def parse_event(line):
    parts = [part.strip() for part in line.split("|")]
    if len(parts) < 4:
        return None
    try:
        stamp = parse_time(parts[0])
    except ValueError:
        return None
    return {
        "time": stamp,
        "project": parts[1],
        "id": parts[2],
        "kind": parts[3],
        "text": parts[4] if len(parts) > 4 else "",
        "raw": line,
    }


def sweep(leaders, lines):
    kept = []
    limit = datetime.now() - STALE
    for item in leaders:
        try:
            beat = parse_time(item.get("heartbeat") or "")
        except ValueError:
            beat = None
        if beat is not None and beat >= limit:
            kept.append(item)
            continue
        append_event(lines, item.get("project"), item.get("id"), "stale", "超时退出")
    return kept, lines


def find_leader(leaders, agent_id):
    for item in leaders:
        if item.get("id") == agent_id:
            return item
    return None


def touch(item):
    item["heartbeat"] = now_text()


def online_same_project(leaders, project):
    key = project_key(project)
    return [item for item in leaders if project_key(item.get("project")) == key]


#-------------#
# 命令
#-------------#
def cmd_join(args):
    project = args.project.strip()
    if not project:
        print("NEED project")
        return 1
    status = args.status
    wait_for = (args.wait_for or "").strip()
    if status == "waiting" and not wait_for:
        print("NEED wait-for")
        return 1
    with RoomLock():
        leaders = load_leaders()
        lines = load_lines()
        leaders, lines = sweep(leaders, lines)
        current = find_leader(leaders, args.id)
        stamp = now_text()
        same_wait = (
            current
            and current.get("status") == "waiting"
            and status == "waiting"
            and project_key(current.get("project")) == project_key(project)
            and project_key(current.get("wait_for")) == project_key(wait_for)
        )
        since = current.get("since") if same_wait else stamp
        record = {
            "id": args.id,
            "project": project,
            "status": status,
            "task": " ".join((args.task or "").split()),
            "wait_for": wait_for if status == "waiting" else "",
            "resources": split_resources(args.resources),
            "since": since,
            "heartbeat": stamp,
        }
        if same_wait and current.get("hold_until"):
            record["hold_until"] = current["hold_until"]
        if current:
            leaders = [item for item in leaders if item.get("id") != args.id]
        leaders.append(record)
        append_event(lines, project, args.id, "join", f"{status} {record['task']}".strip())
        save_leaders(leaders)
        save_lines(lines)
    print(f"JOINED {project} {status}")
    return 0


def cmd_beat(args):
    with RoomLock():
        leaders = load_leaders()
        lines = load_lines()
        leaders, lines = sweep(leaders, lines)
        current = find_leader(leaders, args.id)
        if current:
            touch(current)
        save_leaders(leaders)
        save_lines(lines)
    print("BEAT" if current else "ABSENT")
    return 0


def cmd_say(args):
    text = " ".join(args.text.split())
    if not text:
        print("NEED text")
        return 1
    if args.to:
        text = f"to={args.to.strip()} {text}"
    with RoomLock():
        leaders = load_leaders()
        lines = load_lines()
        leaders, lines = sweep(leaders, lines)
        current = find_leader(leaders, args.id)
        project = current.get("project") if current else "-"
        if current:
            touch(current)
        append_event(lines, project, args.id, "say", text)
        save_leaders(leaders)
        save_lines(lines)
    print("SAID")
    return 0


def cmd_done(args):
    project = args.project.strip()
    if not project:
        print("NEED project")
        return 1
    with RoomLock():
        leaders = load_leaders()
        lines = load_lines()
        leaders, lines = sweep(leaders, lines)
        current = find_leader(leaders, args.id)
        if current:
            touch(current)
        append_event(lines, project, args.id, "done", "")
        save_leaders(leaders)
        save_lines(lines)
    print(f"DONE {project}")
    return 0


def cmd_leave(args):
    reason = " ".join((args.reason or "").split()) or "leave"
    with RoomLock():
        leaders = load_leaders()
        lines = load_lines()
        leaders, lines = sweep(leaders, lines)
        current = find_leader(leaders, args.id)
        if current:
            leaders = [item for item in leaders if item.get("id") != args.id]
            append_event(lines, current.get("project"), args.id, "leave", reason)
        save_leaders(leaders)
        save_lines(lines)
    print("LEFT" if current else "ABSENT")
    return 0


def format_online(leaders):
    if not leaders:
        return ["(空)"]
    rows = []
    for item in leaders:
        resources = ",".join(item.get("resources") or [])
        rows.append(
            f"{item.get('project')} | {item.get('status')} | id={item.get('id')} | "
            f"wait_for={item.get('wait_for') or '-'} | task={item.get('task') or '-'} | "
            f"resources={resources or '-'} | since={item.get('since')} | heartbeat={item.get('heartbeat')}"
        )
    return rows


def cmd_read(args):
    with RoomLock():
        leaders = load_leaders()
        lines = load_lines()
        leaders, lines = sweep(leaders, lines)
        if args.id:
            current = find_leader(leaders, args.id)
            if current:
                touch(current)
        save_leaders(leaders)
        save_lines(lines)
        tail = lines[-40:]
    print("ONLINE")
    print("\n".join(format_online(leaders)))
    print("ROOM")
    print("\n".join(tail) if tail else "(空)")
    return 0


def later_events(lines, project, kind, after):
    found = []
    key = project_key(project)
    for line in lines:
        event = parse_event(line)
        if not event or event["time"] <= after:
            continue
        if project_key(event["project"]) != key or event["kind"] != kind:
            continue
        found.append(event)
    return found


def cmd_wait(args):
    project = args.project.strip()
    if not project:
        print("NEED project")
        return 1
    timeout = args.timeout if args.timeout is not None else WAIT_MAX
    interval = args.interval if args.interval is not None else POLL
    deadline = time.time() + timeout
    while True:
        with RoomLock():
            leaders = load_leaders()
            lines = load_lines()
            leaders, lines = sweep(leaders, lines)
            current = find_leader(leaders, args.id)
            if not current:
                save_leaders(leaders)
                save_lines(lines)
                print("ABSENT")
                return 1
            touch(current)
            try:
                after = parse_time(current.get("since") or "")
            except ValueError:
                after = datetime.now()
            done = later_events(lines, project, "done", after)
            hold_line = None
            if done and current.get("status") == "waiting":
                current["status"] = "working"
                current["wait_for"] = ""
                current["hold_until"] = ""
            elif not done:
                try:
                    hold_after = parse_time(current.get("hold_until") or "")
                except ValueError:
                    hold_after = after
                if hold_after < after:
                    hold_after = after
                gone = later_events(lines, project, "leave", hold_after)
                gone += later_events(lines, project, "stale", hold_after)
                if gone and not online_same_project(leaders, project):
                    current["hold_until"] = gone[-1]["time"].strftime("%Y-%m-%d %H:%M:%S")
                    hold_line = gone[-1]["raw"]
            save_leaders(leaders)
            save_lines(lines)
        if done:
            print(f"READY project={project} at {done[-1]['time'].strftime('%Y-%m-%d %H:%M:%S')}")
            return 0
        if hold_line:
            print(f"HOLD project={project} left without done: {hold_line}")
            return 2
        if time.time() >= deadline:
            print(f"TIMEOUT project={project} still waiting")
            return 3
        time.sleep(interval)


def addressed_to(event, agent_id):
    if not event or event["kind"] != "say" or event["id"] == agent_id:
        return False
    text = event["text"]
    token = f"to={agent_id}"
    return text == token or text.startswith(token + " ")


def fresh_say(event, say_after, skip_equal, printed):
    if not event or event["raw"] in printed:
        return False
    if event["time"] < say_after:
        return False
    if skip_equal and event["time"] == say_after:
        return False
    return True


def listen_until(args, timeout, quiet="TIMEOUT", hold_say=False):
    interval = args.interval if args.interval is not None else POLL
    beat_every = args.beat if args.beat is not None else BEAT_EVERY
    if beat_every <= 0 or beat_every >= int(STALE.total_seconds()):
        print("NEED beat under 45 minutes")
        return 1
    deadline = time.time() + timeout
    next_beat = time.time()
    say_after = datetime.now()
    skip_equal = True
    printed = set()
    while True:
        with RoomLock():
            leaders = load_leaders()
            lines = load_lines()
            leaders, lines = sweep(leaders, lines)
            current = find_leader(leaders, args.id)
            if not current:
                save_leaders(leaders)
                save_lines(lines)
                print("ABSENT", flush=True)
                return 1
            if time.time() >= next_beat:
                touch(current)
                next_beat = time.time() + beat_every
            says = []
            for line in lines:
                event = parse_event(line)
                if not fresh_say(event, say_after, skip_equal, printed):
                    continue
                if addressed_to(event, args.id):
                    says.append(event)
            done = []
            wait_for = (current.get("wait_for") or "").strip()
            if current.get("status") == "waiting" and wait_for:
                try:
                    after = parse_time(current.get("since") or "")
                except ValueError:
                    after = say_after
                done = later_events(lines, wait_for, "done", after)
            save_leaders(leaders)
            save_lines(lines)
        if says:
            for event in says:
                print(f"SAY {event['raw']}", flush=True)
                printed.add(event["raw"])
            if not hold_say:
                return 0
            say_after = max(event["time"] for event in says)
            skip_equal = False
            if time.time() >= deadline:
                return 3
        if done:
            stamp = done[-1]["time"].strftime("%Y-%m-%d %H:%M:%S")
            print(f"READY project={wait_for} at {stamp}", flush=True)
            return 0
        if time.time() >= deadline:
            print(f"{quiet} listen still quiet", flush=True)
            return 3
        time.sleep(interval)


def cmd_listen(args):
    timeout = args.timeout if args.timeout is not None else WAIT_MAX
    return listen_until(args, timeout, quiet="TIMEOUT")


def cmd_watch(args):
    cycle = args.timeout if args.timeout is not None else WAIT_MAX
    total = args.max if args.max is not None else WATCH_MAX
    if cycle <= 0 or total <= 0:
        print("NEED positive timeout and max")
        return 1
    end = time.time() + total
    while True:
        left = end - time.time()
        if left <= 0:
            print("TIMEOUT watch still quiet", flush=True)
            return 3
        code = listen_until(
            args, max(1, int(min(cycle, left))), quiet="CHECK", hold_say=True
        )
        if code != 3:
            return code
        if time.time() >= end:
            print("TIMEOUT watch still quiet", flush=True)
            return 3


#-------------#
# 参数
#-------------#
def build_parser():
    parser = argparse.ArgumentParser(description="组长房间")
    sub = parser.add_subparsers(dest="cmd", required=True)

    join = sub.add_parser("join")
    join.add_argument("--id", required=True)
    join.add_argument("--project", required=True)
    join.add_argument("--task", default="")
    join.add_argument("--status", choices=("working", "waiting"), default="working")
    join.add_argument("--wait-for", default="")
    join.add_argument("--resources", default="")
    join.set_defaults(func=cmd_join)

    beat = sub.add_parser("beat")
    beat.add_argument("--id", required=True)
    beat.set_defaults(func=cmd_beat)

    say = sub.add_parser("say")
    say.add_argument("--id", required=True)
    say.add_argument("--text", required=True)
    say.add_argument("--to", default="")
    say.set_defaults(func=cmd_say)

    read = sub.add_parser("read")
    read.add_argument("--id", default="")
    read.set_defaults(func=cmd_read)

    done = sub.add_parser("done")
    done.add_argument("--id", required=True)
    done.add_argument("--project", required=True)
    done.set_defaults(func=cmd_done)

    wait = sub.add_parser("wait")
    wait.add_argument("--id", required=True)
    wait.add_argument("--project", required=True)
    wait.add_argument("--timeout", type=int)
    wait.add_argument("--interval", type=int)
    wait.set_defaults(func=cmd_wait)

    listen = sub.add_parser("listen")
    listen.add_argument("--id", required=True)
    listen.add_argument("--timeout", type=int)
    listen.add_argument("--interval", type=int)
    listen.add_argument("--beat", type=int)
    listen.set_defaults(func=cmd_listen)

    watch = sub.add_parser("watch")
    watch.add_argument("--id", required=True)
    watch.add_argument("--timeout", type=int)
    watch.add_argument("--max", type=int)
    watch.add_argument("--interval", type=int)
    watch.add_argument("--beat", type=int)
    watch.set_defaults(func=cmd_watch)

    leave = sub.add_parser("leave")
    leave.add_argument("--id", required=True)
    leave.add_argument("--reason", default="")
    leave.set_defaults(func=cmd_leave)
    return parser


def main():
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main() or 0)
