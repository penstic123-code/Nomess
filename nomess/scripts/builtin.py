"""docgen 的内置生成器,nomess.json 里写 {"file": ..., "builtin": "名字"}:
  lessons-index  教训库目录里每个主题页一行:标题 + 条数
  agents-entry   AGENTS.md 的 nomess 段:设计总览和系统图在哪、提交前自动检查、教训怎么查、文档写在哪;有总排期(大项目)多一行会话协议
  memory-index   {"dir": 记忆目录}:每个主题页一行 [标题](文件)
  docs-index     全部文档按类型分组的目录(放 <docs_root>/overview.md 末尾),见 doctypes.py
"""
import os
import posixpath
import re

import nm_config
from messages import t


def _title(text, name):
    m = re.search(r"^#[ \t]+(.+)$", text, re.M)
    return m.group(1).strip() if m else os.path.splitext(name)[0]


def lessons_index(snap, cfg, spec):
    import lessons
    out = []
    for p in snap.ls(nm_config.lessons_dir(cfg), ".md"):
        name = posixpath.basename(p)
        if name != "README.md":
            text = snap.text(p)
            out.append(t("LESSON_COUNT", _title(text, name), name, len(lessons.parse_text(text, name))))
    return "\n".join(out)


def memory_index(snap, cfg, spec):
    """记忆目录一般在仓库外(项目记忆目录),这一个生成器读磁盘、不走快照。"""
    d = os.path.join(snap.root, spec["dir"])
    skip = ("MEMORY.md", "INDEX.md")
    out = []
    for p in nm_config.glob_files(d, "*.md"):
        if os.path.basename(p) not in skip:
            with open(p, encoding="utf-8", errors="replace") as f:
                out.append("- [%s](%s)" % (_title(f.read(), os.path.basename(p)), os.path.basename(p)))
    return "\n".join(out)


def agents_entry(snap, cfg, spec):
    """入口段(上限 12 行):固定三行 + “什么写在哪”两行(按类型表生成,13.12 第 2 条);大项目(有总排期)多一行会话协议。
    inbox 提醒行已去掉(它只在主分支提交时刷新,本来就不准;lessons_remind 留给自动整理)。升降档建议不进入口段(只在 status 和状态栏)。"""
    import doctypes
    import map as nm_map
    exp = nm_config.expanded(cfg)
    ov, smap, sched = doctypes.overview(exp), nm_map.out_dir(exp) + "/index.md", exp["docs_root"] + "/schedule.md"
    out = [t("ENTRY_1", ov, smap) if snap.isfile(ov) else t("ENTRY_1B", smap), t("ENTRY_2"), t("ENTRY_3")]  # 总览页按需建,有才提
    out += doctypes.where_lines(exp)
    if snap.isfile(sched):
        out.append(t("ENTRY_4", sched))
    return "\n".join(out)


GENERATORS = {
    "lessons-index": lessons_index,
    "memory-index": memory_index,
    "agents-entry": agents_entry,
    # >>> P22 只在这两行之间追加
    # <<< P22
    # >>> P24 只在这两行之间追加
    "owners": __import__("arch").owners,  # 生成器写在 arch.py(区块外不加 import)
    # <<< P24
    # >>> R2 只在这两行之间追加
    "docs-index": __import__("doctypes").docs_index,  # 写在 doctypes.py(区块外不加 import)
    # <<< R2
}


def produce(snap, cfg, spec):
    name = spec["builtin"]
    if name not in GENERATORS:
        raise KeyError(t("NO_BUILTIN", name, ", ".join(GENERATORS)))
    return GENERATORS[name](snap, cfg, spec)
