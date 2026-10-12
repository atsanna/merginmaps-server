#!/usr/bin/env python3
# Copyright (C) 2026 merginmaps-server contributors
#
# SPDX-License-Identifier: AGPL-3.0-only
"""Update roadmap step status: python3 site/set_status.py <step> <done|wip|todo> [<step> <status> ...]"""

import datetime
import json
import os
import sys

path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "roadmap.json")
with open(path, encoding="utf-8") as f:
    data = json.load(f)
pairs = dict(zip(sys.argv[1::2], sys.argv[2::2]))
for phase in data["phases"]:
    for step in phase["steps"]:
        if step["n"] in pairs:
            assert pairs[step["n"]] in ("done", "wip", "todo")
            step["status"] = pairs.pop(step["n"])
assert not pairs, f"unknown steps: {pairs}"
data["updated"] = datetime.date.today().isoformat()
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
