"""docgen 的内置生成器,nomess.json 里写 {"file": ..., "builtin": "名字"}:
  lessons-index  教训库目录里每个主题页一行:标题 + 条数
  agents-entry   AGENTS.md 的 nomess 段:设计总览和系统图在哪、提交前自动检查、教训怎么查;有 docs/schedule.md(大项目)多一行会话协议
  memory-index   {"dir": 记忆目录}:每个主题页一行 [标题](文件)
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
    for p in snap.ls(cfg.get("lessons_dir", "docs/lessons"), ".md"):
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
    """入口段:固定三行;大项目(有 docs/schedule.md)多一行会话协议;inbox 攒到 lessons_remind 条多一行提醒整理。升降档建议不进入口段(只在 status 和状态栏)。"""
    import lessons
    exp = nm_config.expanded(cfg)
    out = [t("ENTRY_1"), t("ENTRY_2"), t("ENTRY_3")]
    if snap.isfile("docs/schedule.md"):
        out.append(t("ENTRY_4"))
    text = snap.text("%s/%s" % (exp["lessons_dir"], lessons.INBOX))
    n = len(lessons.parse_text(text, lessons.INBOX)) if text else 0
    if n >= exp["lessons_remind"]:
        out.append(t("ENTRY_5", n))
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
}


def produce(snap, cfg, spec):
    name = spec["builtin"]
    if name not in GENERATORS:
        raise KeyError(t("NO_BUILTIN", name, ", ".join(GENERATORS)))
    return GENERATORS[name](snap, cfg, spec)
