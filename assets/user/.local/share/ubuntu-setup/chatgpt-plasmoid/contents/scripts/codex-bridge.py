#!/usr/bin/env python3
import argparse
import json
import os
import signal
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

CODEX_HOME = Path(os.environ.get("CODEX_HOME", os.path.expanduser("~/.codex")))
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
STREAM_FILE = RUNTIME_DIR / "codex-plasmoid-stream.json"
PID_FILE = RUNTIME_DIR / "codex-plasmoid.pid"

FALLBACK_MODELS = [
    "default",
    "gpt-6.1-sol",
    "gpt-6.1-terra",
    "gpt-6-astra",
    "gpt-6-chat-thinking",
    "gpt-6-sol",
    "gpt-6-luna",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gpt-5.6-luna",
    "gpt-5.4-mini",
]


def find_codex_bin() -> str:
    for candidate in [
        shutil.which("codex"),
        "/usr/local/bin/codex",
    ]:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return "codex"


def get_login_status() -> dict:
    codex_bin = find_codex_bin()
    try:
        res = subprocess.run(
            [codex_bin, "login", "status"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        out = (res.stdout + "\n" + res.stderr).strip()
        logged_in = res.returncode == 0 and ("Logged in" in out or "logged in" in out.lower())
        return {
            "loggedIn": logged_in,
            "statusText": out.splitlines()[0] if out else ("Logged in" if logged_in else "Not logged in"),
        }
    except Exception as e:
        return {"loggedIn": False, "statusText": f"Error checking login: {e}"}


def get_models() -> list:
    models = ["default"]
    cache_file = CODEX_HOME / "models_cache.json"
    if cache_file.is_file():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            raw_list = data.get("models", []) if isinstance(data, dict) else data
            for m in raw_list:
                if isinstance(m, dict):
                    slug = m.get("slug") or m.get("id")
                    if slug and slug not in models:
                        models.append(slug)
        except Exception:
            pass
    for m in FALLBACK_MODELS:
        if m not in models:
            models.append(m)
    return models


def get_recent_threads(limit: int = 25) -> list:
    threads = []
    state_db = CODEX_HOME / "state_5.sqlite"
    if state_db.is_file():
        try:
            conn = sqlite3.connect(f"file:{state_db}?mode=ro", uri=True, timeout=2.0)
            cur = conn.cursor()
            rows = cur.execute(
                "SELECT id, title, updated_at, cwd FROM threads ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            for tid, title, updated_at, cwd in rows:
                clean_title = " ".join((title or "Untitled Session").split())
                if len(clean_title) > 80:
                    clean_title = clean_title[:77] + "..."
                threads.append(
                    {
                        "id": tid,
                        "title": clean_title,
                        "updatedAt": updated_at,
                        "cwd": cwd or os.path.expanduser("~"),
                    }
                )
            conn.close()
            if threads:
                return threads
        except Exception:
            pass

    idx_file = CODEX_HOME / "session_index.jsonl"
    if idx_file.is_file():
        try:
            lines = idx_file.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in reversed(lines[-limit:]):
                if not line.strip():
                    continue
                obj = json.loads(line)
                threads.append(
                    {
                        "id": obj.get("id", ""),
                        "title": obj.get("thread_name", "Session"),
                        "updatedAt": obj.get("updated_at", ""),
                        "cwd": os.path.expanduser("~"),
                    }
                )
        except Exception:
            pass
    return threads


def load_thread_messages(thread_id: str) -> dict:
    messages = []
    hist_db = CODEX_HOME / "thread_history_1.sqlite"
    cwd = os.path.expanduser("~")
    title = "Session"

    state_db = CODEX_HOME / "state_5.sqlite"
    if state_db.is_file():
        try:
            conn = sqlite3.connect(f"file:{state_db}?mode=ro", uri=True, timeout=2.0)
            row = conn.execute(
                "SELECT title, cwd FROM threads WHERE id = ?", (thread_id,)
            ).fetchone()
            if row:
                title = " ".join((row[0] or "Session").split())[:80]
                cwd = row[1] or cwd
            conn.close()
        except Exception:
            pass

    if hist_db.is_file():
        try:
            conn = sqlite3.connect(f"file:{hist_db}?mode=ro", uri=True, timeout=2.0)
            rows = conn.execute(
                "SELECT item_type, item_json FROM thread_items WHERE thread_id = ? ORDER BY rollout_ordinal ASC",
                (thread_id,),
            ).fetchall()
            for item_type, item_json in rows:
                try:
                    obj = json.loads(item_json)
                except Exception:
                    continue
                if item_type == "userMessage":
                    parts = []
                    for c in obj.get("content", []):
                        if isinstance(c, dict) and c.get("text"):
                            parts.append(c["text"].strip())
                    text = "\n".join(p for p in parts if p)
                    if text:
                        messages.append({"role": "user", "text": text, "meta": ""})
                elif item_type == "agentMessage":
                    text = (obj.get("text") or "").strip()
                    phase = obj.get("phase") or ""
                    if text:
                        if phase == "commentary" and messages and messages[-1]["role"] == "assistant":
                            messages[-1]["text"] += "\n\n" + text
                        else:
                            messages.append(
                                {
                                    "role": "assistant",
                                    "text": text,
                                    "meta": "Commentary" if phase == "commentary" else "",
                                }
                            )
                elif item_type == "commandExecution":
                    cmd = obj.get("command")
                    if isinstance(cmd, list):
                        cmd_str = " ".join(cmd)
                    else:
                        cmd_str = str(cmd or "")
                    if cmd_str:
                        messages.append(
                            {
                                "role": "tool",
                                "text": f"`$ {cmd_str}`",
                                "meta": f"exit {obj.get('exitCode', 0)}" if "exitCode" in obj else "command",
                            }
                        )
            conn.close()
        except Exception:
            pass

    return {
        "threadId": thread_id,
        "title": title,
        "cwd": cwd,
        "messages": messages[-60:],
    }


def write_stream_state(state: dict):
    try:
        tmp = STREAM_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(STREAM_FILE)
    except Exception:
        pass


def run_prompt(args):
    codex_bin = find_codex_bin()
    cwd = os.path.expanduser(args.cwd or "~")
    if not os.path.isdir(cwd):
        cwd = os.path.expanduser("~")

    cmd = [codex_bin, "exec"]
    if args.thread_id:
        cmd.extend(["resume", args.thread_id])
    elif args.resume_last:
        cmd.extend(["resume", "--last"])

    cmd.extend(["--json", "--skip-git-repo-check"])

    if args.model and args.model != "default":
        cmd.extend(["-m", args.model])

    if not args.thread_id and not args.resume_last:
        if args.sandbox:
            cmd.extend(["-s", args.sandbox])
        cmd.extend(["-C", cwd])

    cmd.append(args.prompt)

    stream_state = {
        "running": True,
        "threadId": args.thread_id or "",
        "status": "Starting Codex...",
        "text": "",
        "activities": [],
        "error": "",
        "usage": {},
        "updatedAt": time.time(),
    }
    write_stream_state(stream_state)

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    except Exception as e:
        stream_state["running"] = False
        stream_state["error"] = f"Failed to start codex: {e}"
        stream_state["status"] = "Error"
        write_stream_state(stream_state)
        print(json.dumps(stream_state))
        return

    agent_chunks = []
    activities = []

    try:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue

            ev_type = ev.get("type", "")
            if ev_type == "thread.started":
                stream_state["threadId"] = ev.get("thread_id", stream_state["threadId"])
                stream_state["status"] = "Thinking..."
            elif ev_type == "turn.started":
                stream_state["status"] = "Thinking..."
            elif ev_type in ("item.started", "item.updated", "item.completed"):
                item = ev.get("item") or {}
                itype = item.get("type", "")
                if itype == "reasoning":
                    summary = item.get("text") or ""
                    stream_state["status"] = "Reasoning..."
                    if summary and ev_type == "item.completed":
                        activities.append(f"Thought: {summary[:120]}")
                elif itype in ("command_execution", "commandExecution"):
                    c = item.get("command", "")
                    if isinstance(c, list):
                        c = " ".join(c)
                    stream_state["status"] = f"Running: {c[:60]}"
                    if ev_type == "item.completed":
                        code = item.get("exit_code", item.get("exitCode", 0))
                        activities.append(f"`$ {c}` (exit {code})")
                elif itype in ("file_change", "fileChange"):
                    stream_state["status"] = "Editing files..."
                    if ev_type == "item.completed":
                        activities.append("Updated workspace files")
                elif itype in ("mcp_tool_call", "mcpToolCall", "web_search", "webSearch"):
                    stream_state["status"] = f"Using tool ({itype})..."
                    if ev_type == "item.completed":
                        activities.append(f"Tool: {itype}")
                elif itype in ("agent_message", "agentMessage"):
                    txt = (item.get("text") or "").strip()
                    if txt:
                        if ev_type == "item.completed":
                            agent_chunks.append(txt)
                            stream_state["text"] = "\n\n".join(agent_chunks)
                        else:
                            preview = "\n\n".join(agent_chunks + [txt])
                            stream_state["text"] = preview
                        stream_state["status"] = "Responding..."
            elif ev_type == "turn.completed":
                stream_state["usage"] = ev.get("usage") or {}
                stream_state["status"] = "Completed"
            elif ev_type == "error":
                err_msg = ev.get("message") or str(ev)
                stream_state["error"] = err_msg

            stream_state["activities"] = activities[-8:]
            stream_state["updatedAt"] = time.time()
            write_stream_state(stream_state)

        stderr_out = proc.stderr.read().strip() if proc.stderr else ""
        ret = proc.wait()
        if ret != 0 and not stream_state["text"] and not stream_state["error"]:
            stream_state["error"] = stderr_out or f"Codex exited with status {ret}"
    except Exception as e:
        stream_state["error"] = str(e)
    finally:
        if PID_FILE.exists():
            try:
                PID_FILE.unlink()
            except Exception:
                pass
        stream_state["running"] = False
        if not stream_state["status"] or stream_state["status"] not in ("Completed", "Stopped"):
            stream_state["status"] = "Idle"
        stream_state["updatedAt"] = time.time()
        write_stream_state(stream_state)

    print(json.dumps(stream_state))


def stop_running():
    stopped = False
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            os.kill(pid, signal.SIGTERM)
            stopped = True
        except Exception:
            pass
        try:
            PID_FILE.unlink()
        except Exception:
            pass
    if STREAM_FILE.exists():
        try:
            state = json.loads(STREAM_FILE.read_text(encoding="utf-8"))
            state["running"] = False
            state["status"] = "Stopped"
            write_stream_state(state)
        except Exception:
            pass
    print(json.dumps({"stopped": stopped}))


def open_tui(thread_id: str, cwd: str, model: str):
    codex_bin = find_codex_bin()
    work_dir = os.path.expanduser(cwd or "~")
    if not os.path.isdir(work_dir):
        work_dir = os.path.expanduser("~")

    codex_cmd = [codex_bin]
    if model and model != "default":
        codex_cmd.extend(["-m", model])
    if thread_id:
        codex_cmd.extend(["resume", thread_id])

    for term_bin, term_args in [
        ("kitty", ["kitty", "--title", "Codex CLI", "--working-directory", work_dir] + codex_cmd),
        ("alacritty", ["alacritty", "--title", "Codex CLI", "--working-directory", work_dir, "-e"] + codex_cmd),
        ("konsole", ["konsole", "--workdir", work_dir, "-e"] + codex_cmd),
    ]:
        resolved = shutil.which(term_bin) or f"/usr/bin/{term_bin}"
        if os.path.isfile(resolved) and os.access(resolved, os.X_OK):
            term_args[0] = resolved
            subprocess.Popen(term_args, start_new_session=True)
            print(json.dumps({"launched": True, "terminal": term_bin}))
            return

    print(json.dumps({"launched": False, "error": "No supported terminal emulator found"}))


def run_login(action: str):
    codex_bin = find_codex_bin()
    if action == "logout":
        subprocess.run([codex_bin, "logout"], capture_output=True, text=True)
        print(json.dumps(get_login_status()))
        return

    # Launch `codex login` in a background process (opens browser for ChatGPT OAuth)
    subprocess.Popen([codex_bin, "login"], start_new_session=True)
    time.sleep(1.0)
    print(json.dumps(get_login_status()))


def main():
    parser = argparse.ArgumentParser(description="Plasma 6 Codex CLI Bridge")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    sub.add_parser("status")
    sub.add_parser("stop")
    sub.add_parser("stream-state")

    p_load = sub.add_parser("load-thread")
    p_load.add_argument("--thread-id", required=True)

    p_send = sub.add_parser("send")
    p_send.add_argument("--prompt", required=True)
    p_send.add_argument("--thread-id", default="")
    p_send.add_argument("--resume-last", action="store_true")
    p_send.add_argument("--model", default="default")
    p_send.add_argument("--sandbox", default="workspace-write")
    p_send.add_argument("--cwd", default="~")

    p_tui = sub.add_parser("open-tui")
    p_tui.add_argument("--thread-id", default="")
    p_tui.add_argument("--cwd", default="~")
    p_tui.add_argument("--model", default="default")

    p_auth = sub.add_parser("auth")
    p_auth.add_argument("--action", choices=["login", "logout"], default="login")

    p_copy = sub.add_parser("copy")
    p_copy.add_argument("--text", required=True)

    args = parser.parse_args()

    if args.cmd == "init":
        info = {
            "auth": get_login_status(),
            "models": get_models(),
            "threads": get_recent_threads(25),
        }
        print(json.dumps(info))
    elif args.cmd == "status":
        print(json.dumps(get_login_status()))
    elif args.cmd == "load-thread":
        print(json.dumps(load_thread_messages(args.thread_id)))
    elif args.cmd == "send":
        run_prompt(args)
    elif args.cmd == "stop":
        stop_running()
    elif args.cmd == "stream-state":
        if STREAM_FILE.is_file():
            try:
                print(STREAM_FILE.read_text(encoding="utf-8"))
            except Exception:
                print(json.dumps({"running": False}))
        else:
            print(json.dumps({"running": False}))
    elif args.cmd == "open-tui":
        open_tui(args.thread_id, args.cwd, args.model)
    elif args.cmd == "auth":
        run_login(args.action)
    elif args.cmd == "copy":
        for clip_cmd in [["wl-copy"], ["xclip", "-selection", "clipboard"]]:
            if shutil.which(clip_cmd[0]):
                subprocess.run(clip_cmd, input=args.text, text=True)
                break
        print(json.dumps({"copied": True}))


if __name__ == "__main__":
    main()
