"""生成物落盘的唯一入口(refresh、map、rules、docgen、提交钩子都调 apply)。不导入 githook / map / rules / docgen。
目录策略(空目录要不要删)不在这里:由拥有输出目录的命令自己调 prune_empty。"""
import os
import subprocess
import sys

import nm_config
import snapshot
from messages import t


def _blob(root, data):
    p = subprocess.run(["git", "hash-object", "-w", "--stdin", "--no-filters"], cwd=root, input=data, capture_output=True)
    if p.returncode:
        raise snapshot.SnapshotError("git hash-object: " + p.stderr.decode("utf-8", "replace").strip())
    return p.stdout.decode().strip()


def _zero_oid(root):
    """删除记录用的全零对象名,长度随仓库的哈希算法。"""
    p = subprocess.run(["git", "rev-parse", "--show-object-format"], cwd=root, capture_output=True, text=True)
    return "0" * (64 if p.stdout.strip() == "sha256" else 40)


def apply(root, changes, cand=None, index_only=False):
    """changes: {路径: bytes | None(删)}。动手前先确认每个目标都不经过链接(只查本次 changes)。
    cand 不给:只原子写工作区、删多余的旧文件;逐个尝试,失败的不中断后面的,最后抛一个汇总全部失败路径的 OSError。
    cand 给了(提交钩子,cand 是检查过的候选树):先把同样的字节写成 blob(--no-filters,不经 clean filter),按候选树里的模式
    一次 update-index --index-info 写进索引(路径是字面量,不经 pathspec);索引更新失败抛 SnapshotError,什么都没动。
    成功后再写工作区;写失败的路径汇总成一行黄,提交照常(索引里已是检查过的内容)。
    index_only(要同时给 cand):只更新索引、不写工作区、不碰链接以外的磁盘(钩子里写回"工作区本来就该保持原样"的内容,例如基线跟着改名走)。"""
    if index_only and cand is None:
        raise ValueError("outwrite.apply: index_only needs cand")
    for rel in changes:
        nm_config.no_link(root, rel)
    if cand is not None:
        modes, recs = cand.files(), []
        zero = _zero_oid(root) if None in changes.values() else None
        for rel, data in changes.items():
            if data is None:
                recs.append("0 %s\t%s" % (zero, rel))
            else:
                recs.append("%s %s\t%s" % (modes[rel], _blob(root, data), rel))
        p = subprocess.run(["git", "update-index", "-z", "--index-info"], cwd=root, capture_output=True,
                           input="".join(r + "\0" for r in recs).encode("utf-8", "surrogateescape"))
        if p.returncode:
            raise snapshot.SnapshotError("git update-index: " + p.stderr.decode("utf-8", "replace").strip())
    if index_only:
        return
    failed = []
    for rel, data in changes.items():
        full = os.path.join(root, rel)
        try:
            if data is not None:
                nm_config.atomic_write(full, data)
            elif os.path.lexists(full):
                os.remove(full)
        except OSError as e:
            failed.append("%s (%s)" % (rel, e.strerror or e))
    if failed:
        msg = ", ".join(failed)
        if cand is None:
            raise OSError(msg)
        print(t("GH_WT_FAIL", msg), file=sys.stderr)


def prune_empty(root, rel):
    """输出目录空了就删(不空或不存在时 rmdir 自己失败,什么都不做)。由拥有这个目录的命令调。"""
    try:
        os.rmdir(os.path.join(root, rel))
    except OSError:
        pass
