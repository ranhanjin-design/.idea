"""Manual smoke script: print pass/fail for representative midterm behaviors."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["PAWPLAN_FORCE_DEV"] = "1"

from fastapi.testclient import TestClient

from pawplan.agent.dev_fallback import run_dev_fallback
from pawplan.api.main import app
from pawplan.database.db import init_database


def check(name: str, cond: bool, detail: str = "") -> bool:
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    return cond


def main() -> int:
    init_database()
    client = TestClient(app)
    ok = True

    # 1) API health
    h = client.get("/api/health").json()
    ok &= check(
        "health.status=ok",
        h.get("status") == "ok",
        f"restaurants={h['database'].get('restaurants')} parks={h['database'].get('parks')}",
    )
    ok &= check(
        "cuisine_filter enabled",
        h.get("capabilities", {}).get("cuisine_filter") is True,
    )
    ok &= check(
        "cuisine_recommendation disabled",
        h.get("capabilities", {}).get("cuisine_recommendation") is False,
    )

    cases = [
        (
            "knowledge+source",
            "带狗散步时，怎样降低中暑风险？",
            lambda r, t: t
            and t[0]["tool"] == "search_knowledge"
            and "来源" in r
            and "核实日期" in r
            and "http" in r,
        ),
        (
            "filter stock no tools",
            "可以总结一下今天的股票市场吗？",
            lambda r, t: t == [] and "范围" in r,
        ),
        (
            "restaurant district+source",
            "沙田有没有获准让狗进入的食肆？",
            lambda r, t: t
            and t[0]["tool"] == "search_restaurants"
            and t[0]["arguments"].get("district") == "Sha Tin"
            and "cuisine" not in t[0]["arguments"]
            and "地区" in r
            and "核实日期" in r
            and "fehd.gov.hk" in r.lower(),
        ),
        (
            "park district+source",
            "沙田有没有宠物公园？",
            lambda r, t: t
            and t[0]["tool"] == "search_parks"
            and t[0]["arguments"].get("district") == "Sha Tin"
            and "来源" in r
            and "核实日期" in r,
        ),
        (
            "cuisine filter honest",
            "找一家沙田附近的点心店",
            lambda r, t: t
            and t[0]["tool"] == "search_restaurants"
            and t[0]["arguments"].get("cuisine") == "dim_sum"
            and "获准食肆示例" not in r
            and ("无法确认" in r or "非正式官方" in r)
            and ("改查" in r or "愿意" in r),
        ),
        (
            "no-result restaurant",
            "南极洲有没有获准让狗进入的食肆？",
            lambda r, t: t
            and t[0]["tool"] == "search_restaurants"
            and t[0]["result_count"] == 0
            and ("暂无" in r or "没有" in r),
        ),
    ]

    for name, q, pred in cases:
        reply, trace = run_dev_fallback(q)
        passed = bool(pred(reply, trace))
        ok &= check(name, passed, f"tools={[x.get('tool') for x in trace]}")

    # API chat e2e sample
    chat = client.post("/api/chat", json={"message": "帮我预测明天股票"}).json()
    ok &= check(
        "api chat out-of-scope",
        chat.get("tool_trace") == [] and "范围" in chat.get("reply", ""),
        f"mode={chat.get('mode')}",
    )

    print("---")
    print("SMOKE_OK" if ok else "SMOKE_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
