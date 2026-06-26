import html
import json
import os
import re
import time

import ai_rag
import gitinfo
import shellrun
import store
import sysinfo as si

BASE = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE, "data", "ai_chats.json")

SYSTEM_PROMPT = """Ты ИИ-помощник по обслуживанию VPS и проектов в /opt.
Отвечай по-русски, кратко и по делу.
Не выдумывай метрики — используй tools для live-данных и search_docs/read_file для кода.
Shell только для диагностики. Не предлагай rm -rf, reboot, mkfs и разрушительные команды.
Если данных нет — скажи честно."""

_rate_last = {}
_rate_hour = {}


def _cfg(cfg):
    return cfg.get("ai", {})


def _history_path():
    return HISTORY_FILE


def load_history(chat_id, limit=20):
    data = store.load_json(_history_path(), {})
    rows = data.get(str(chat_id), [])
    return rows[-limit:]


def save_history(chat_id, rows, limit=20):
    data = store.load_json(_history_path(), {})
    data[str(chat_id)] = rows[-limit:]
    store.save_json(_history_path(), data)


def clear_history(chat_id):
    data = store.load_json(_history_path(), {})
    data.pop(str(chat_id), None)
    store.save_json(_history_path(), data)


def check_rate(chat_id, ai_cfg):
    now = time.time()
    min_gap = float(ai_cfg.get("min_gap_sec", 3))
    last = _rate_last.get(chat_id, 0)
    if now - last < min_gap:
        return False, "подожди пару секунд"
    _rate_last[chat_id] = now

    hour_key = int(now // 3600)
    bucket = _rate_hour.setdefault(chat_id, {"h": hour_key, "n": 0})
    if bucket["h"] != hour_key:
        bucket = {"h": hour_key, "n": 0}
        _rate_hour[chat_id] = bucket
    max_h = int(ai_cfg.get("max_per_hour", 30))
    if bucket["n"] >= max_h:
        return False, "лимит запросов на час"
    bucket["n"] += 1
    return True, None


def _llm_primary(ai_cfg):
    from langchain_nvidia_ai_endpoints import ChatNVIDIA

    return ChatNVIDIA(
        model=ai_cfg.get("primary_model", "minimaxai/minimax-m3"),
        api_key=os.getenv("NVIDIA_API_KEY", ""),
        temperature=float(ai_cfg.get("temperature", 0.4)),
        top_p=0.95,
        max_completion_tokens=int(ai_cfg.get("max_tokens", 4096)),
    )


def _llm_fallback(ai_cfg):
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=ai_cfg.get("fallback_model", "meta-llama/llama-3.3-70b-instruct:free"),
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        base_url="https://openrouter.ai/api/v1",
        temperature=float(ai_cfg.get("temperature", 0.4)),
        max_tokens=int(ai_cfg.get("max_tokens", 4096)),
    )


def _invoke_llm(ai_cfg, messages):
    errs = []
    if os.getenv("NVIDIA_API_KEY"):
        try:
            return _llm_primary(ai_cfg).invoke(messages), "nvidia"
        except Exception as e:
            errs.append(f"nvidia: {e}")
    if os.getenv("OPENROUTER_API_KEY"):
        try:
            return _llm_fallback(ai_cfg).invoke(messages), "openrouter"
        except Exception as e:
            errs.append(f"openrouter: {e}")
    raise RuntimeError("; ".join(errs) or "no API keys")


def _tool_search_docs(query, ai_cfg):
    hits = ai_rag.search(query, ai_cfg, k=5)
    if not hits:
        return "ничего не найдено в индексе"
    lines = []
    for h in hits:
        src = h.get("source", "?")
        txt = h.get("text", "")[:600]
        lines.append(f"### {src}\n{txt}")
    return "\n\n".join(lines)


def _tool_server_snapshot():
    snap = si.snapshot()
    return json.dumps({
        "disk_pct": snap["disk_pct"],
        "ram_pct": snap["ram_pct"],
        "load": snap["load_str"],
        "uptime": si.uptime_line(),
        "mem": si.mem_info(),
        "disk_root": si.disk_root(),
        "ip": si.local_ip(),
    }, ensure_ascii=False)


def _tool_project_status():
    return json.dumps(store.get_all_projects(), ensure_ascii=False)


def _tool_service_logs(unit, lines, cfg):
    allowed = {s["unit"] for s in cfg.get("services", [])}
    if unit not in allowed:
        return f"unit not allowed, pick from: {', '.join(sorted(allowed))}"
    return si.tail_journal(unit, min(int(lines), 40))[:3500]


def _tool_list_dir(path, ai_cfg):
    real = ai_rag.safe_path(path, ai_cfg)
    if not real or not os.path.isdir(real):
        return "path not allowed or missing"
    try:
        rows = sorted(os.listdir(real))[:80]
        return "\n".join(rows)
    except Exception as e:
        return str(e)


def _tool_read_file(path, ai_cfg, max_chars=8000):
    real = ai_rag.safe_path(path, ai_cfg)
    if not real or not os.path.isfile(real):
        return "file not allowed or missing"
    try:
        with open(real, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()[:max_chars]
    except Exception as e:
        return str(e)


def _tool_git_summary(cfg):
    return gitinfo.format_git(cfg.get("git_dirs", []))


def _tool_run_command(cmd, chat_id, cfg):
    out, code = shellrun.run(cmd, chat_id, cfg.get("shell", {}))
    return f"exit={code}\n{out}"


def _extract_tool_call(text):
    m = re.search(r"<tool>([a-z_]+)</tool>\s*<args>(.*?)</args>", text, re.S | re.I)
    if not m:
        return None, None
    name = m.group(1).strip().lower()
    raw = m.group(2).strip()
    try:
        args = json.loads(raw) if raw.startswith("{") else {"q": raw}
    except Exception:
        args = {"q": raw}
    return name, args


def _run_tool(name, args, chat_id, cfg, ai_cfg):
    if name == "search_docs":
        return _tool_search_docs(args.get("query") or args.get("q", ""), ai_cfg)
    if name == "server_snapshot":
        return _tool_server_snapshot()
    if name == "project_status":
        return _tool_project_status()
    if name == "service_logs":
        return _tool_service_logs(args.get("unit", ""), args.get("lines", 20), cfg)
    if name == "list_dir":
        return _tool_list_dir(args.get("path", "/opt/telegramvps"), ai_cfg)
    if name == "read_file":
        return _tool_read_file(args.get("path", ""), ai_cfg)
    if name == "git_summary":
        return _tool_git_summary(cfg)
    if name == "run_command":
        return _tool_run_command(args.get("command") or args.get("cmd", ""), chat_id, cfg)
    return f"unknown tool: {name}"


def _offline_snapshot():
    snap = si.snapshot()
    return (
        "AI offline. Live snapshot:\n"
        f"disk {snap['disk_pct']}% · ram {snap['ram_pct']}% · load {snap['load_str']}\n"
        f"{si.mem_info()}\n{si.disk_root()}"
    )


def _build_messages(history, question, cfg, ai_cfg):
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    tool_help = (
        "Доступные tools — ответь тегом <tool>name</tool> <args>{json}</args> если нужны данные:\n"
        "search_docs {query}, server_snapshot {}, project_status {}, "
        "service_logs {unit, lines}, list_dir {path}, read_file {path}, "
        "git_summary {}, run_command {command}"
    )
    msgs = [SystemMessage(content=SYSTEM_PROMPT + "\n\n" + tool_help)]
    for row in history:
        if row["role"] == "user":
            msgs.append(HumanMessage(content=row["content"]))
        else:
            msgs.append(AIMessage(content=row["content"]))
    msgs.append(HumanMessage(content=question))
    return msgs


def ask(question, chat_id, cfg):
    ai_cfg = _cfg(cfg)
    if not ai_cfg.get("enabled", True):
        return "AI disabled in config"

    ok, err = check_rate(chat_id, ai_cfg)
    if not ok:
        return err

    limit = int(ai_cfg.get("history_limit", 20))
    history = load_history(chat_id, limit)

    try:
        from langchain_core.messages import AIMessage, HumanMessage

        msgs = _build_messages(history, question, cfg, ai_cfg)
        answer = ""
        provider = "?"

        for _ in range(3):
            resp, provider = _invoke_llm(ai_cfg, msgs)
            text = (resp.content or "").strip()
            tool_name, tool_args = _extract_tool_call(text)
            if not tool_name:
                answer = text
                break
            tool_out = _run_tool(tool_name, tool_args or {}, chat_id, cfg, ai_cfg)
            msgs.append(AIMessage(content=text))
            msgs.append(HumanMessage(content=f"[tool {tool_name} result]\n{tool_out[:6000]}"))
        else:
            resp, provider = _invoke_llm(ai_cfg, msgs)
            answer = (resp.content or "").strip()

        if not answer:
            answer = "пустой ответ от модели"

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
        save_history(chat_id, history, limit)
        return f"{answer}\n\n<i>via {provider}</i>"
    except Exception:
        return _offline_snapshot()


def build_daily_report(cfg):
    snap = _tool_server_snapshot()
    projects = _tool_project_status()
    prompt = (
        "Сделай краткий daily report по VPS (5-8 пунктов, русский):\n"
        f"server: {snap}\nprojects: {projects}\n"
        "Дай рекомендации если ram/disk > 70%."
    )
    ai_cfg = _cfg(cfg)
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        msgs = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        resp, provider = _invoke_llm(ai_cfg, msgs)
        body = (resp.content or "").strip()
        return f"🤖 <b>Daily AI report</b>\n\n{html.escape(body)}\n\n<i>via {provider}</i>"
    except Exception:
        return f"🤖 <b>Daily report</b>\n<pre>{html.escape(_offline_snapshot())}</pre>"


def format_reply(text, limit=4000):
    if len(text) <= limit:
        return [text]
    chunks = []
    block = ""
    for line in text.split("\n"):
        cand = f"{block}\n{line}".strip() if block else line
        if len(cand) > limit and block:
            chunks.append(block)
            block = line
        else:
            block = cand
    if block:
        chunks.append(block)
    return chunks or [text[:limit]]


def ensure_index(cfg, force=False):
    ai_cfg = _cfg(cfg)
    if not ai_cfg.get("enabled", True):
        return 0
    chunks, _ = ai_rag.rebuild_index(ai_cfg, force=force)
    return len(chunks)