"""快照读取的唯一入口:配置、基线、源文件一律经这里读,不在别处直接 open / git show。
三种来源,接口一样:
  open_snapshot(root, "index")            索引(git 钩子里用;沿用环境里的 GIT_INDEX_FILE,不自己拼 .git/index;按 git write-tree 的树读)
  open_snapshot(root, "tree", ref)        某个提交的树(CI、读 HEAD 基线)
  open_snapshot(root, "worktree")         工作区(手动 nomess check;已跟踪 + 未跟踪未忽略的文件,尊重 .gitignore)
只读普通文件:符号链接(120000)和子模块(160000)只在 files() 里出现、带自己的模式,read() 返回 None,不读内容。
路径一律相对仓库根、用 / 分隔。root 必须是仓库顶层(用 toplevel() 取)。"""
import hashlib
import os
import subprocess

REGULAR = ("100644", "100755")
SYMLINK, GITLINK = "120000", "160000"
PRIVATE = ".nomess/"  # nomess 自己的本机目录(缓存等):不进任何快照清单


def blob_hash(data):
    """内容的 git 式对象名(sha1("blob <长度>\0" + 字节)):没有 oid 的条目(工作区、叠加内容)用它,和 cache 共用一个算法。"""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


class SnapshotError(Exception):
    pass


def _git(root, *args):
    p = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if p.returncode:
        raise SnapshotError("git %s: %s" % (" ".join(args[:2]), p.stderr.decode("utf-8", "replace").strip()))
    return p.stdout


def _path(b):
    return b.decode("utf-8", "surrogateescape")


def has_commit(root, ref):
    """ref 能解析成提交(还没有提交时 HEAD 不能)。"""
    return subprocess.run(["git", "rev-parse", "--verify", "-q", ref + "^{commit}"], cwd=root, capture_output=True).returncode == 0


def toplevel(cwd):
    """cwd 所在仓库的顶层目录(正斜杠);不在仓库里抛 SnapshotError。"""
    return _path(_git(cwd, "rev-parse", "--show-toplevel")).strip()


class Snapshot:
    """source: "index" | "tree" | "worktree"。files() 的结果在对象生命周期内不变(工作区读的是首次调用时的磁盘清单)。
    用完调 close()(或 with)以关掉 cat-file 子进程。"""

    def __init__(self, root, source, ref=None):
        if source not in ("index", "tree", "worktree"):
            raise ValueError("unknown snapshot source %r" % source)
        if (source == "tree") != (ref is not None):
            raise ValueError("ref is required for tree and only for tree")
        self.root, self.source, self.ref = root, source, ref
        self._entries = None  # path -> (mode, oid | None(工作区,读磁盘) | bytes(叠加的内容))
        self._cat = None
        self._parent = None   # overlay() 派生出的快照:父快照 + 改动
        self._changes = {}
        self._tree_id = None  # index 来源:git write-tree 写出的树

    def _tree(self):
        """index / tree 来源对应的树。索引按 git write-tree 读:和将要提交的树一致(intent-to-add 条目不在里面);
        有未合并条目时 write-tree 失败、抛 SnapshotError。"""
        if self.source == "tree":
            return self.ref
        if self._tree_id is None:
            self._tree_id = _git(self.root, "write-tree").decode().strip()
        return self._tree_id

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def close(self):
        if self._parent:
            self._parent.close()
        if self._cat:
            self._cat.stdin.close()
            self._cat.stdout.close()
            self._cat.wait()
            self._cat = None

    def _load(self):
        if self._entries is not None:
            return self._entries
        e = {}
        if self._parent:
            e = dict(self._parent._load())
            for p, data in self._changes.items():
                if data is None:
                    e.pop(p, None)
                else:
                    old = e.get(p, ("100644",))[0]
                    e[p] = (old if old in REGULAR else "100644", data)
            self._entries = e
            return e
        if self.source != "worktree":
            for rec in _git(self.root, "ls-tree", "-r", "-z", "--full-tree", self._tree()).split(b"\0")[:-1]:
                meta, p = rec.split(b"\t", 1)
                mode, _type, oid = meta.decode().split()
                e[_path(p)] = (mode, oid)
        else:
            names = _git(self.root, "ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\0")[:-1]
            # core.fileMode=false(Windows 缺省)时磁盘上没有可信的可执行位,已跟踪文件取索引里的模式
            idx = {}
            if subprocess.run(["git", "config", "--bool", "core.fileMode"], cwd=self.root,
                              capture_output=True).stdout.strip() == b"false":
                for rec in _git(self.root, "ls-files", "-s", "-z").split(b"\0")[:-1]:
                    meta, p = rec.split(b"\t", 1)
                    idx[_path(p)] = meta.split()[0].decode()
            for p in map(_path, names):
                if p.startswith(PRIVATE):
                    continue
                full = os.path.join(self.root, p)
                try:
                    st = os.lstat(full)
                except OSError:
                    continue  # 已跟踪但工作区删了
                if os.path.islink(full):
                    mode = SYMLINK
                elif os.path.isdir(full):
                    mode = GITLINK
                elif idx.get(p) in REGULAR:
                    mode = idx[p]
                else:
                    mode = "100755" if (st.st_mode & 0o111 and os.name != "nt") else "100644"
                e[p] = (mode, None)
        self._entries = e
        return e

    def files(self):
        """{路径: 模式},模式是 git 的六位八进制字符串:100644 / 100755 / 120000(符号链接)/ 160000(子模块)。
        索引和树的模式是 git 记录的;工作区:core.fileMode=false 时已跟踪文件取索引里的模式,否则由磁盘的可执行位推出,未跟踪文件在 Windows 上恒 100644。"""
        return {p: m for p, (m, _o) in self._load().items()}

    def read(self, path):
        """普通文件返回内容 bytes;路径不存在、符号链接、子模块返回 None(用 files() 区分)。"""
        ent = self._load().get(path)
        if ent is None or ent[0] not in REGULAR:
            return None
        if isinstance(ent[1], bytes):
            return ent[1]
        if self._parent:
            return self._parent.read(path)
        if self.source == "worktree":
            with open(os.path.join(self.root, path), "rb") as f:
                return f.read()
        if self._cat is None:
            self._cat = subprocess.Popen(["git", "cat-file", "--batch"], cwd=self.root, stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE)
        self._cat.stdin.write(ent[1].encode() + b"\n")
        self._cat.stdin.flush()
        head = self._cat.stdout.readline().split()
        if len(head) != 3:
            raise SnapshotError("cat-file: no object for %s (%s)" % (path, ent[1]))
        data = self._cat.stdout.read(int(head[2]))
        self._cat.stdout.read(1)  # 结尾换行
        return data

    def overlay(self, changes):
        """派生快照:bytes 表示新增或替换(模式沿用原文件的,原来没有取 100644),None 表示删除。不改本快照;
        派生快照共用本快照的 cat-file 进程,只需关派生的(close 会连带关父)。"""
        o = Snapshot(self.root, self.source, self.ref)
        o._parent, o._changes = self, dict(changes)
        return o

    def changed(self, base="HEAD"):
        """{路径: 状态},相对 base 改动过的:A 新增 / M 修改(含类型变化)/ D 删除。不认重命名:记成旧路径 D + 新路径 A。
        index / tree:base 的树对本快照的树;worktree:git diff base 加未跟踪文件;
        叠加快照再并入叠加的路径(内容和模式都和 base 相同的不算改动)。base 不存在(还没有提交)时全部算 A。"""
        if not has_commit(self.root, base):
            return {p: "A" for p in self.files()}
        if self._parent:
            out = dict(self._parent.changed(base))
            mine = self.files()
            with Snapshot(self.root, "tree", base) as b:
                old = b.files()
                for p, data in self._changes.items():
                    out.pop(p, None)
                    if data is None:
                        if p in old:
                            out[p] = "D"
                    elif p not in old:
                        out[p] = "A"
                    elif old[p] != mine[p] or b.read(p) != data:
                        out[p] = "M"
            return out
        if self.source == "worktree":
            raw = _git(self.root, "diff", "-z", "--name-status", "--no-renames", base)
        else:
            raw = _git(self.root, "diff-tree", "-r", "-z", "--name-status", "--no-renames", base, self._tree())
        tok = raw.split(b"\0")
        out = {_path(tok[i + 1]): "M" if tok[i] == b"T" else tok[i].decode() for i in range(0, len(tok) - 1, 2)}
        if self.source == "worktree":
            for p in map(_path, _git(self.root, "ls-files", "-z", "--others", "--exclude-standard").split(b"\0")[:-1]):
                if not p.startswith(PRIVATE):
                    out[p] = "A"
        return out

    def oid(self, path):
        """普通文件在索引 / 树里记的对象名;工作区和叠加的内容没有(返回 None),要的话读出字节用 blob_hash 算。"""
        ent = self._load().get(path)
        return ent[1] if ent is not None and ent[0] in REGULAR and isinstance(ent[1], str) else None

    def diff(self, base):
        """{路径: A | M | D},本快照相对另一个快照 base(None = 空树)。两边都有对象名就比对象名,否则比字节;
        普通工作区对树走 git diff(用 git 的 stat 缓存,不读全部文件)。"""
        if base is None:
            return {p: "A" for p in self.files()}
        if self.source == "worktree" and not self._parent and base.source == "tree" and not base._parent:
            return self.changed(base.ref)
        mine, old = self._load(), base._load()
        out = {}
        for p in mine.keys() | old.keys():
            if p not in old:
                out[p] = "A"
            elif p not in mine:
                out[p] = "D"
            elif mine[p][0] != old[p][0]:
                out[p] = "M"
            else:
                a, b = self.oid(p), base.oid(p)
                if (a != b) if (a and b) else (self.read(p) != base.read(p)):
                    out[p] = "M"
        return out

    def renames(self, base):
        """{新路径: 旧路径}:git 按相似度(缺省 50%)认出的改名;base 为 None 时为空。工作区只认已跟踪文件的改名;
        叠加快照取父快照的结果、去掉被叠加覆盖的路径。基线跟着改名走(check.py)用它。"""
        if base is None:
            return {}
        if self._parent:
            return {n: o for n, o in self._parent.renames(base).items() if n not in self._changes and o not in self._changes}
        if self.source == "worktree":
            raw = _git(self.root, "diff", "-z", "--name-status", "-M", base._tree())
        else:
            raw = _git(self.root, "diff-tree", "-r", "-z", "--name-status", "-M", base._tree(), self._tree())
        tok, out, i = raw.split(b"\0"), {}, 0
        while i < len(tok) - 1:
            if tok[i][:1] in (b"R", b"C"):
                if tok[i][:1] == b"R":
                    out[_path(tok[i + 2])] = _path(tok[i + 1])
                i += 3
            else:
                i += 2
        return out

    def isfile(self, path):
        """path 是快照里的普通文件。"""
        return self.files().get(path) in REGULAR

    def ls(self, d, suffix="", recursive=False):
        """目录 d(相对仓库根,"" 是根)下的普通文件路径,排序;recursive 为假只列直接子文件。目录、符号链接、子模块不列。"""
        pre = d.strip("/") + "/" if d.strip("/") else ""
        return sorted(p for p, m in self.files().items() if m in REGULAR and p.startswith(pre) and p.endswith(suffix)
                      and (recursive or "/" not in p[len(pre):]))

    def isdir(self, d):
        pre = d.strip("/") + "/"
        return any(p.startswith(pre) for p in self.files())

    def text(self, path):
        """read() 按 UTF-8 解码(不合法字节替换);读不到返回 None。换行原样,比较前交给 docgen.same 统一。"""
        b = self.read(path)
        return None if b is None else b.decode("utf-8", "replace")


def open_snapshot(root, source, ref=None):
    return Snapshot(root, source, ref)
