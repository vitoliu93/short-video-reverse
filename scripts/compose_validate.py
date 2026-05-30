#!/usr/bin/env python3
"""校验 icccut_draft 的每条 action,复用兄弟仓 icccut-agents 的真实校验器。

**须在 icccut-agents venv 内跑**(才有其 deps + 参考 MD 解析):
  uv run --directory /Users/liujiaxi/codebase/icc/kox-base/icccut-agents \
      python <svr>/scripts/compose_validate.py <draft.json>

也供 import:`validate_draft(draft) -> list[(action_type, id, errors)]`(errors 空=过)。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ICC = Path("/Users/liujiaxi/codebase/icc/kox-base/icccut-agents")
sys.path.insert(0, str(ICC / ".claude/skills/draft-manager/scripts"))
from validate_action import validate_action  # noqa: E402


def validate_draft(draft: dict):
    out = []
    for blk in draft.get("script", []):
        for a in blk.get("actions", []):
            errs = validate_action(a, a.get("action_type"))
            out.append((a.get("action_type"), a.get("id"), errs))
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: compose_validate.py <draft.json>", file=sys.stderr)
        sys.exit(2)
    draft = json.loads(Path(sys.argv[1]).read_text())
    results = validate_draft(draft)
    npass = sum(1 for _, _, e in results if not e)
    nfail = len(results) - npass
    for atype, aid, errs in results:
        if errs:
            print(f"  ✗ {atype:11} {aid} -> {errs}")
    print(f"PASS {npass} / FAIL {nfail} (total {len(results)})")
    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    main()
