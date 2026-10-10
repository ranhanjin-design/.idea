import json
import os
from typing import Any

from openai import OpenAI

from pawplan.agent.dev_fallback import run_dev_fallback, try_followup_from_history
from pawplan.agent.logutil import log_event
from pawplan.agent.prompts import SYSTEM_PROMPT
from pawplan.agent.tools_schema import TOOLS
from pawplan.tools.search_knowledge import search_knowledge
from pawplan.tools.search_parks import search_parks
from pawplan.tools.search_places import search_places
from pawplan.tools.search_restaurants import search_restaurants

_ALLOWED_HISTORY_ROLES = {"user", "assistant"}
_HISTORY_TURN_CAP = 12
_HISTORY_CONTENT_MAX = 4000


def _sanitize_history(history: list | None) -> list[dict[str, str]]:
    if not history:
        return []
    cleaned: list[dict[str, str]] = []
    for item in history:
        if isinstance(item, dict):
            role = item.get("role")
            content = item.get("content")
        else:
            role = getattr(item, "role", None)
            content = getattr(item, "content", None)
        if role not in _ALLOWED_HISTORY_ROLES:
            continue
        text = str(content or "").strip()
        if not text:
            continue
        cleaned.append({"role": role, "content": text[:_HISTORY_CONTENT_MAX]})
    return cleaned[-_HISTORY_TURN_CAP:]


def _dispatch_tool(name: str, arguments: dict[str, Any]) -> dict:
    if name == "search_knowledge":
        return search_knowledge(**arguments)
    if name == "search_parks":
        return search_parks(**arguments)
    if name == "search_places":
        kwargs = {
            "district": arguments["district"],
            "limit": int(arguments.get("limit", 5)),
        }
        if arguments.get("place_type"):
            kwargs["place_type"] = arguments["place_type"]
        return search_places(**kwargs)
    if name == "search_restaurants":
        kwargs = {
            "district": arguments["district"],
            "limit": int(arguments.get("limit", 5)),
        }
        if arguments.get("cuisine"):
            kwargs["cuisine"] = arguments["cuisine"]
        return search_restaurants(**kwargs)
    return {"error": "unknown_tool", "name": name}


def run_agent(user_question: str, history: list | None = None) -> dict:
    """
    Returns {"reply": str, "mode": "deepseek"|"dev", "tool_trace": list}.
    """
    sanitized = _sanitize_history(history)

    # Short replies like "1" must not depend on the model remembering options.
    followed = try_followup_from_history(user_question, sanitized)
    if followed is not None:
        reply, trace = followed
        log_event(
            {
                "mode": "followup",
                "user": user_question,
                "tool_trace": trace,
                "reply_preview": reply[:240],
            }
        )
        return {"reply": reply, "mode": "followup", "tool_trace": trace}

    force_dev = os.environ.get("PAWPLAN_FORCE_DEV", "").strip() in {"1", "true", "TRUE", "yes"}
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if force_dev or not api_key:
        reply, trace = run_dev_fallback(user_question, history=sanitized)
        log_event(
            {
                "mode": "dev",
                "user": user_question,
                "tool_trace": trace,
                "reply_preview": reply[:240],
            }
        )
        return {"reply": reply, "mode": "dev", "tool_trace": trace}

    max_steps = int(os.environ.get("MAX_TOOL_STEPS", "4"))
    client = OpenAI(
        api_key=api_key,
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *sanitized,
        {"role": "user", "content": user_question},
    ]
    tool_trace: list[dict] = []

    for _ in range(max_steps):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
        )
        message = response.choices[0].message

        if not message.tool_calls:
            reply = message.content or ""
            log_event(
                {
                    "mode": "deepseek",
                    "user": user_question,
                    "tool_trace": tool_trace,
                    "reply_preview": reply[:240],
                }
            )
            return {
                "reply": reply,
                "mode": "deepseek",
                "tool_trace": tool_trace,
            }

        messages.append(message.model_dump(exclude_none=True))

        for call in message.tool_calls:
            args = json.loads(call.function.arguments)
            result = _dispatch_tool(call.function.name, args)
            if call.function.name == "search_restaurants":
                used = {
                    "district": args.get("district"),
                    "limit": int(args.get("limit", 5)),
                }
                if args.get("cuisine"):
                    used["cuisine"] = args["cuisine"]
            else:
                used = args
            tool_trace.append(
                {
                    "tool": call.function.name,
                    "arguments": used,
                    "result_count": result.get("count"),
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )

    reply = "在工具调用次数上限内未能完成请求，请简化问题后重试。"
    log_event(
        {
            "mode": "deepseek",
            "user": user_question,
            "tool_trace": tool_trace,
            "reply_preview": reply,
            "error": "tool_step_limit",
        }
    )
    return {
        "reply": reply,
        "mode": "deepseek",
        "tool_trace": tool_trace,
    }
