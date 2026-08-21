#!/usr/bin/env python3
"""Per-request token usage breakdown for current Claude Code session."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

_BUILTIN_PRICES = {
    "claude-fable-5":    {"input": 10.00, "cache_write": 12.50, "cache_read": 1.00, "output": 50.00},
    "claude-mythos-5":   {"input": 10.00, "cache_write": 12.50, "cache_read": 1.00, "output": 50.00},
    "claude-opus-4-8":   {"input":  5.00, "cache_write":  6.25, "cache_read": 0.50, "output": 25.00},
    "claude-opus-4-7":   {"input":  5.00, "cache_write":  6.25, "cache_read": 0.50, "output": 25.00},
    "claude-opus-4-6":   {"input":  5.00, "cache_write":  6.25, "cache_read": 0.50, "output": 25.00},
    "claude-sonnet-4-6": {"input":  3.00, "cache_write":  3.75, "cache_read": 0.30, "output": 15.00},
    "claude-haiku-4-5":  {"input":  1.00, "cache_write":  1.25, "cache_read": 0.10, "output":  5.00},
}
_DEFAULT_PRICE = {"input": 3.00, "cache_write": 3.75, "cache_read": 0.30, "output": 15.00}

_CONTEXT_WINDOWS = {
    "claude-haiku-4-5": 200_000,
}
_DEFAULT_CONTEXT_WINDOW = 1_000_000

_PRICES_FILE = Path.home() / ".claude" / "scripts" / "prices.json"

def _load_prices():
    prices = dict(_BUILTIN_PRICES)
    if _PRICES_FILE.exists():
        try:
            prices.update(json.loads(_PRICES_FILE.read_text()))
        except Exception:
            pass
    return prices

PRICES = _load_prices()


def find_session(session_id=None):
    projects = Path.home() / ".claude" / "projects"
    if session_id:
        for p in projects.rglob(f"{session_id}*.jsonl"):
            return p
        print(f"Session {session_id} not found")
        sys.exit(1)
    files = list(projects.rglob("*.jsonl"))
    if not files:
        print("No sessions found")
        sys.exit(1)
    return max(files, key=lambda f: f.stat().st_mtime)


def get_session_desc(path, max_msgs=3):
    snippets = []
    try:
        with open(path) as f:
            for line in f:
                if len(snippets) >= max_msgs:
                    break
                try:
                    e = json.loads(line)
                    if e.get("type") == "user" and not e.get("isSidechain"):
                        content = e.get("message", {}).get("content", "")
                        text = get_text(content).strip().replace("\n", " ")
                        if text and not text.startswith("<"):
                            snippets.append(text[:35])
                except Exception:
                    continue
    except Exception:
        pass
    return "、".join(snippets) if snippets else ""


def list_sessions(sort_by_cost=False, last_n=20, with_desc=False):
    projects = Path.home() / ".claude" / "projects"
    files = sorted(projects.rglob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    rows = []
    for f in files:
        calls = parse_calls(f)
        if not calls:
            continue
        cost = sum(calc_cost(r) for r in calls)
        date = calls[-1]["timestamp"][:10] if calls else "?"
        desc = get_session_desc(f) if with_desc else ""
        rows.append((f.stem[:8], date, len(calls), cost, desc))
    if sort_by_cost:
        rows.sort(key=lambda x: x[3], reverse=True)
    total = len(rows)
    rows = rows[:last_n]
    label = f"最新 {len(rows)} 筆（共 {total} 筆）" if total > last_n else f"{len(rows)} sessions"
    if with_desc:
        print(f"\n{'Session':<12}  {'Date':<10}  {'Calls':>5}  {'Cost':>8}  描述")
        print("─" * 80)
        for stem, date, n, cost, desc in rows:
            print(f"{stem:<12}  {date:<10}  {n:>5}  ${cost:.4f}  {desc}")
    else:
        print(f"\n{'Session':<12}  {'Date':<10}  {'Calls':>6}  {'Cost':>9}  {label}")
        print("─" * 44)
        for stem, date, n, cost, desc in rows:
            print(f"{stem:<12}  {date:<10}  {n:>6}  ${cost:.4f}")
    print()


def show_call(path, r):
    target_ts = r["timestamp"]
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    entries.sort(key=lambda e: e.get("timestamp", ""))

    target_idx = None
    for i, e in enumerate(entries):
        if e.get("type") == "assistant" and e.get("timestamp", "") == target_ts:
            target_idx = i
            break
    if target_idx is None:
        for i, e in enumerate(entries):
            if e.get("type") == "assistant" and e.get("timestamp", "")[:19] == target_ts[:19]:
                target_idx = i
                break
    if target_idx is None:
        print("Entry not found")
        return

    user_text = "(not found)"
    for i in range(target_idx - 1, -1, -1):
        e = entries[i]
        if e.get("type") == "user" and not e.get("isSidechain"):
            text = get_text(e.get("message", {}).get("content", ""))
            if text.strip():
                user_text = text
                break

    content = entries[target_idx].get("message", {}).get("content", [])
    asst_text = ""
    thinking_text = ""
    tool_uses = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                asst_text += block.get("text", "")
            elif btype == "thinking":
                thinking_text += block.get("thinking", "")
            elif btype == "tool_use":
                name = block.get("name", "?")
                inp = block.get("input", {})
                hint = ""
                if "command" in inp:
                    hint = inp["command"][:80]
                elif "file_path" in inp:
                    hint = inp["file_path"]
                tool_uses.append(f"{name}({hint})" if hint else name)
    elif isinstance(content, str):
        asst_text = content

    cost = calc_cost(r)
    ts = r["timestamp"][:19].replace("T", " ")
    print(f"\n── #{r.get('_idx','')} {ts}  {r['model']}  ${cost:.4f} ──")
    print(f"\n[User]\n{user_text[:600]}")
    if len(user_text) > 600:
        print(f"... ({len(user_text)} chars total)")
    if asst_text:
        print(f"\n[Assistant]\n{asst_text[:600]}")
        if len(asst_text) > 600:
            print(f"... ({len(asst_text)} chars total)")
    if tool_uses:
        print(f"\n[Tools]\n" + "\n".join(f"  {t}" for t in tool_uses))
    if thinking_text and not asst_text and not tool_uses:
        print(f"\n[Thinking]\n{thinking_text[:300]}...")
    if not asst_text and not tool_uses and not thinking_text:
        print("\n[Assistant] (no content)")
    print()


def parse_all_sessions():
    projects = Path.home() / ".claude" / "projects"
    files = sorted(projects.rglob("*.jsonl"), key=lambda f: f.stat().st_mtime)
    all_calls = []
    for f in files:
        calls = parse_calls(f)
        sid = f.stem[:8]
        for r in calls:
            r["session"] = sid
        all_calls.extend(calls)
    all_calls.sort(key=lambda r: r["timestamp"])
    return all_calls


def get_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return block.get("text", "")
    return ""


def parse_calls(path):
    entries = []
    seen = set()
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                uid = e.get("uuid") or e.get("requestId")
                if uid and uid in seen:
                    continue
                if uid:
                    seen.add(uid)
                entries.append(e)
            except json.JSONDecodeError:
                continue

    entries.sort(key=lambda e: e.get("timestamp", ""))

    # Build uuid→entry map for prompt lookup
    uuid_map = {e.get("uuid"): e for e in entries if e.get("uuid")}

    calls = []
    last_user_prompt = ""

    for e in entries:
        t = e.get("type")

        if t == "user" and not e.get("isSidechain"):
            content = e.get("message", {}).get("content", "")
            if isinstance(content, list) and all(
                isinstance(b, dict) and b.get("type") != "text" for b in content
            ):
                continue
            prompt = get_text(content).replace("\n", " ").strip()
            if prompt:
                last_user_prompt = prompt

        elif t == "assistant":
            usage = e.get("message", {}).get("usage")
            if not usage:
                continue

            prompt = last_user_prompt
            if len(prompt) > 40:
                prompt = prompt[:37] + "..."

            cc  = usage.get("cache_creation", {})
            stu = usage.get("server_tool_use", {})

            calls.append({
                "timestamp":   e.get("timestamp", ""),
                "session":     "",
                "prompt":      prompt,
                "model":       e.get("message", {}).get("model", ""),
                "input":       usage.get("input_tokens", 0),
                "cache_read":  usage.get("cache_read_input_tokens", 0),
                "cache_write": usage.get("cache_creation_input_tokens", 0),
                "output":      usage.get("output_tokens", 0),
                "cache_1h":    cc.get("ephemeral_1h_input_tokens", 0),
                "cache_5m":    cc.get("ephemeral_5m_input_tokens", 0),
                "web_search":  stu.get("web_search_requests", 0),
                "web_fetch":   stu.get("web_fetch_requests", 0),
                "tier":        usage.get("service_tier", "n/a"),
                "speed":       usage.get("speed", "n/a"),
                "geo":         usage.get("inference_geo", "n/a"),
            })

    return calls


def calc_cost(r):
    p = PRICES.get(r.get("model", ""), _DEFAULT_PRICE)
    M = 1_000_000
    return (
        r["input"]       * p["input"]       / M +
        r["cache_write"] * p["cache_write"] / M +
        r["cache_read"]  * p["cache_read"]  / M +
        r["output"]      * p["output"]      / M
    )


def fmt_k(n):
    return f"{n/1000:.1f}K" if n >= 1000 else str(n)

def fmt_kc(n, cost):
    return f"{fmt_k(n)}(${cost:.2f})"


def pipe_to_pager(text):
    pager = os.environ.get("PAGER", "less")
    try:
        proc = subprocess.Popen([pager, "-R"], stdin=subprocess.PIPE)
        proc.communicate(text.encode())
    except FileNotFoundError:
        print(text, end="")


def paginate(lines, page_size):
    total = len(lines)
    for i, line in enumerate(lines):
        print(line)
        if (i + 1) % page_size == 0 and i + 1 < total:
            try:
                ans = input(f"\n── {i+1}/{total} 筆 ── Enter 繼續 / q 離開: ")
                if ans.strip().lower() == "q":
                    break
            except (EOFError, KeyboardInterrupt):
                print()
                break


def main():
    args = sys.argv[1:]

    # --set-price <model> <input> <output>  (cache rates auto-derived)
    if len(args) >= 4 and args[0] == "--set-price":
        model = args[1] if args[1].startswith("claude-") else f"claude-{args[1]}"
        inp, out = float(args[2]), float(args[3])
        entry = {"input": inp, "cache_write": round(inp * 1.25, 4),
                 "cache_read": round(inp * 0.10, 4), "output": out}
        data = json.loads(_PRICES_FILE.read_text()) if _PRICES_FILE.exists() else {}
        data[model] = entry
        _PRICES_FILE.write_text(json.dumps(data, indent=2))
        print(f"Updated {model}: input=${inp} output=${out} (prices.json)")
        sys.exit(0)

    last_n = None
    summary = False
    detail = False
    pager = False
    page_size = None
    reverse = False
    sort_cost = False
    show_n = None
    list_sessions_flag = False
    recall_flag = False
    current_flag = False
    watch_flag = False
    session_id = None
    for a in args:
        if a.startswith("--last="):
            last_n = int(a.split("=")[1])
        elif a == "--last":
            last_n = 1
        elif a == "--summary":
            summary = True
        elif a == "--detail":
            detail = True
        elif a == "--pager":
            pager = True
        elif a == "--reverse" or a == "-r":
            reverse = True
        elif a == "--sort=cost" or a == "--sort-cost":
            sort_cost = True
        elif a.startswith("--page-size=") or a.startswith("--ps="):
            page_size = int(a.split("=")[1])
        elif a.startswith("--show="):
            show_n = int(a.split("=")[1])
        elif a == "--sessions":
            list_sessions_flag = True
        elif a == "--recall":
            recall_flag = True
        elif a == "--current":
            current_flag = True
        elif a == "--watch":
            watch_flag = True
        else:
            session_id = a

    if watch_flag:
        path = find_session()
        calls = parse_calls(path)
        if not calls:
            sys.exit(0)
        r = calls[-1]
        cost = calc_cost(r)
        p = PRICES.get(r.get("model", ""), _DEFAULT_PRICE)
        M = 1_000_000
        model_short = r["model"].replace("claude-", "")
        in_c  = fmt_kc(r['input'],       r['input']       * p['input']       / M)
        cr_c  = fmt_kc(r['cache_read'],  r['cache_read']  * p['cache_read']  / M)
        cw_c  = fmt_kc(r['cache_write'], r['cache_write'] * p['cache_write'] / M)
        out_c = fmt_kc(r['output'],      r['output']      * p['output']      / M)
        ctx_tokens = r['input'] + r['cache_read']
        ctx_limit = _CONTEXT_WINDOWS.get(r.get("model", ""), _DEFAULT_CONTEXT_WINDOW)
        ctx_pct = int(ctx_tokens / ctx_limit * 100)
        print(f"⌚ {model_short}  In:{in_c}  CR:{cr_c}  CW:{cw_c}  Out:{out_c}  =${cost:.4f}  ctx:{ctx_pct}%")
        sys.exit(0)

    if recall_flag:
        list_sessions(sort_by_cost=sort_cost, last_n=last_n if last_n is not None else 10, with_desc=True)
        sys.exit(0)

    if list_sessions_flag:
        list_sessions(sort_by_cost=sort_cost, last_n=last_n if last_n is not None else 20)
        sys.exit(0)

    no_session_arg = not session_id
    if current_flag:
        path = find_session()
        calls = parse_calls(path)
        session_id = path.stem[:8]
        no_session_arg = False
    elif session_id:
        path = find_session(session_id)
        calls = parse_calls(path)
        for r in calls:
            r["session"] = path.stem[:8]
    else:
        path = find_session()
        calls = parse_all_sessions()

    if not calls:
        print("No token data found in session")
        sys.exit(0)

    total_calls = len(calls)
    if last_n is not None:
        calls = calls[-last_n:]
    if sort_cost:
        calls = sorted(calls, key=calc_cost, reverse=True)
    elif reverse:
        calls = list(reversed(calls))

    for i, r in enumerate(calls, 1):
        r["_idx"] = i

    if show_n is not None:
        if 1 <= show_n <= len(calls):
            show_call(path, calls[show_n - 1])
        else:
            print(f"#{show_n} out of range (1–{len(calls)})")
        sys.exit(0)

    session_name = path.stem[:8]
    date = calls[0]["timestamp"][:10] if calls[0]["timestamp"] else "?"
    shown = len(calls)
    if last_n and total_calls > last_n:
        label = f"最新 {shown} 筆（共 {total_calls} 筆）"
    elif last_n:
        label = f"最新 {shown} 筆"
    else:
        label = f"{shown} API calls"

    # Aggregate totals
    total = {k: 0 for k in ("input","cache_read","cache_write","output","web_search","web_fetch")}
    total_costs = {"input": 0.0, "cache_read": 0.0, "cache_write": 0.0, "output": 0.0}
    for r in calls:
        for k in total:
            total[k] += r[k]
        p = PRICES.get(r.get("model", ""), _DEFAULT_PRICE)
        M = 1_000_000
        total_costs["input"]       += r["input"]       * p["input"]       / M
        total_costs["cache_read"]  += r["cache_read"]  * p["cache_read"]  / M
        total_costs["cache_write"] += r["cache_write"] * p["cache_write"] / M
        total_costs["output"]      += r["output"]      * p["output"]      / M

    total_cost = sum(total_costs.values())

    buf = io.StringIO() if (pager or page_size) else None
    if buf:
        sys.stdout = buf

    print(f"\n📊 oct-usage  |  {label}\n")

    if summary:
        # Aggregated summary table
        cache_1h_total = sum(r["cache_1h"] for r in calls)
        cache_5m_total = sum(r["cache_5m"] for r in calls)
        models = sorted(set(r["model"] for r in calls if r["model"]))
        tiers  = sorted(set(r["tier"]  for r in calls if r["tier"]))
        speeds = sorted(set(r["speed"] for r in calls if r["speed"]))
        geos   = sorted(set(r["geo"]   for r in calls if r["geo"]))
        print(f"  model:  {', '.join(models) or 'n/a'}")
        print(f"  tier:   {', '.join(tiers)  or 'n/a'}")
        print(f"  speed:  {', '.join(speeds) or 'n/a'}")
        print(f"  geo:    {', '.join(geos)   or 'n/a'}")
        print()
        M = 1_000_000
        rows = [
            ("input",          total["input"],       total["input"]       * _DEFAULT_PRICE["input"]       / M, _DEFAULT_PRICE["input"]),
            ("cache_read",     total["cache_read"],  total["cache_read"]  * _DEFAULT_PRICE["cache_read"]  / M, _DEFAULT_PRICE["cache_read"]),
            ("cache_write",    total["cache_write"], total["cache_write"] * _DEFAULT_PRICE["cache_write"] / M, _DEFAULT_PRICE["cache_write"]),
            ("cache_write_1h", cache_1h_total,       cache_1h_total       * _DEFAULT_PRICE["cache_write"] / M, _DEFAULT_PRICE["cache_write"]),
            ("cache_write_5m", cache_5m_total,       cache_5m_total       * _DEFAULT_PRICE["cache_write"] / M, _DEFAULT_PRICE["cache_write"]),
            ("output",         total["output"],      total["output"]      * _DEFAULT_PRICE["output"]      / M, _DEFAULT_PRICE["output"]),
            ("web_search",     total["web_search"],  0.0, 0),
            ("web_fetch",      total["web_fetch"],   0.0, 0),
        ]
        print(f"{'Type':<18} {'Tokens':>12} {'$/MTok':>8} {'Cost':>10}")
        print("─" * 52)
        for name, tokens, cost, rate in rows:
            rate_str = f"{rate:.2f}" if rate else "-"
            cost_str = f"${cost:>9.4f}" if rate else f"{'(n/a)':>10}"
            print(f"{name:<18} {tokens:>12,} {rate_str:>8} {cost_str}")
        print("─" * 52)
        print(f"{'Total':<18} {'':>12} {'':>8} ${total_cost:>9.4f}")
    else:
        # Table view
        model_w = max((len(r["model"].replace("claude-","")) for r in calls), default=8)
        show_session = no_session_arg  # show Session col when browsing all sessions

        sess_col = f"  {'Session':<8}" if show_session else ""
        if detail:
            hdr = f"  {'#':>3}  {'Timestamp':<19}{sess_col}  {'Model':<{model_w}}  {'In':>6}  {'CacheRead':>7}  {'CacheWrite':>7}  {'1h':>7}  {'5m':>7}  {'Out':>6}  {'🔍':>2}  {'🌐':>2}  {'Tier':<8}  {'Speed':<8}  {'Cost':>7}"
        else:
            hdr = f"  {'#':>3}  {'Timestamp':<19}{sess_col}  {'Model':<{model_w}}  {'In':>12}  {'CacheRead':>14}  {'CacheWrite':>15}  {'Out':>13}  {'Cost':>8}"
        print(hdr)
        print("─" * len(hdr))

        for i, r in enumerate(calls, 1):
            cost = calc_cost(r)
            model_short = r["model"].replace("claude-", "")
            ts = r["timestamp"][:19].replace("T", " ") if r["timestamp"] else "n/a"
            sc = f"  {r.get('session',''):<8}" if show_session else ""
            if detail:
                ws = str(r["web_search"]) if r["web_search"] else "-"
                wf = str(r["web_fetch"])  if r["web_fetch"]  else "-"
                print(f"  {i:>3}  {ts:<19}{sc}  {model_short:<{model_w}}  {fmt_k(r['input']):>6}  {fmt_k(r['cache_read']):>7}  {fmt_k(r['cache_write']):>7}  {fmt_k(r['cache_1h']):>7}  {fmt_k(r['cache_5m']):>7}  {fmt_k(r['output']):>6}  {ws:>2}  {wf:>2}  {r['tier']:<8}  {r['speed']:<8}  ${cost:.4f}")
            else:
                p = PRICES.get(r.get("model", ""), _DEFAULT_PRICE)
                M = 1_000_000
                in_c  = fmt_kc(r['input'],       r['input']       * p['input']       / M)
                cr_c  = fmt_kc(r['cache_read'],  r['cache_read']  * p['cache_read']  / M)
                cw_c  = fmt_kc(r['cache_write'], r['cache_write'] * p['cache_write'] / M)
                out_c = fmt_kc(r['output'],      r['output']      * p['output']      / M)
                print(f"  {i:>3}  {ts:<19}{sc}  {model_short:<{model_w}}  {in_c:>12}  {cr_c:>14}  {cw_c:>14}  {out_c:>13}  ${cost:.4f}")

        print("─" * len(hdr))
        if len(calls) > 1:
            t_model = ""
            tc = f"  {'':8}" if show_session else ""
            blank = f"  {'':>3}  {'':19}{tc}"
            if detail:
                print(f"{blank}  {'Total':<{model_w}}  {fmt_k(total['input']):>6}  {fmt_k(total['cache_read']):>7}  {fmt_k(total['cache_write']):>7}  {'':>7}  {'':>7}  {fmt_k(total['output']):>6}  {'':>2}  {'':>2}  {'':>8}  {'':>8}  ${total_cost:.4f}")
            else:
                in_tc  = fmt_kc(total['input'],       total_costs['input'])
                cr_tc  = fmt_kc(total['cache_read'],  total_costs['cache_read'])
                cw_tc  = fmt_kc(total['cache_write'], total_costs['cache_write'])
                out_tc = fmt_kc(total['output'],      total_costs['output'])
                print(f"{blank}  {'Total':<{model_w}}  {in_tc:>12}  {cr_tc:>14}  {cw_tc:>14}  {out_tc:>13}  ${total_cost:.4f}")
        if current_flag and calls:
            last = calls[-1]
            ctx = last['input'] + last['cache_read']
            print(f"\n  context now: ~{fmt_k(ctx)} tokens  (In + CacheRead of last call)")
    print()

    if buf:
        sys.stdout = sys.__stdout__
        output = buf.getvalue()
        if pager:
            pipe_to_pager(output)
        else:
            paginate(output.splitlines(), page_size)


if __name__ == "__main__":
    main()
