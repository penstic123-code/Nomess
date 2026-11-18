"""通用缓存:只存从单个文件内容就能得到的原始事实(设计稿 ⑥ 第 4 小节)。各检测器用自己的 kind,提取函数写在自己的文件里。
  facts(snap, path, kind, version, fn)  返回 fn(text);键 = (内容对象名, kind, version)
存 <仓库根>/.nomess/cache/<sha1(json [kind, version])>.json,内容 {"kind", "version", "facts": {对象名: 值}};.nomess/ 不进快照清单。
不加锁:进程退出时原子替换,后写的覆盖先写的;任何读写错误只当没命中(缓存可随时整个删掉)。不回收、不删别的版本。"""
import atexit
import hashlib
import json
import os

import nm_config
import snapshot

_stores = {}  # (root, kind, version) -> [facts, dirty]
_trusted = True  # disable_read() 之后不读磁盘上的缓存(CI:检出目录里的缓存文件不可信),算出的照样写


def disable_read():
    """不读已有的缓存文件,只用本进程算出的事实(--ci 调)。"""
    global _trusted
    _trusted = False


def _file(root, kind, version):
    name = hashlib.sha1(json.dumps([kind, version], ensure_ascii=False).encode("utf-8")).hexdigest()
    return os.path.join(root, ".nomess", "cache", name + ".json")


def _read(root, kind, version):
    try:
        with open(_file(root, kind, version), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}  # 没有或坏了:当空缓存,保存时整个重写
    ok = isinstance(d, dict) and d.get("kind") == kind and d.get("version") == version and isinstance(d.get("facts"), dict)
    return d["facts"] if ok else {}


def _store(root, kind, version):
    k = (root, kind, version)
    if k not in _stores:
        _stores[k] = [_read(root, kind, version) if _trusted else {}, False]
    return _stores[k]


def _copy(v):
    """JSON 值的深拷贝(只有 dict / list / 标量,比 copy.deepcopy 快得多)。"""
    t = type(v)
    if t is list:
        return [_copy(x) for x in v]
    if t is dict:
        return {k: _copy(x) for k, x in v.items()}
    return v


def facts(snap, path, kind, version, fn):
    """fn(text) 的结果,text = 文件字节按 UTF-8 解码(非法字节替换)、\\r\\n 换成 \\n。fn 的结果若还依赖文本以外的东西(扩展名、配置),
    要写进 kind 或 version。读不到(不是普通文件)返回 None,不调 fn、不写缓存。值必须能存成 JSON;没命中时返回的也是 JSON 往返后的值,
    命中与否类型一致;返回的是副本,调用者改了不影响缓存。有对象名的(索引 / 树,工作区里相对索引没改过的已跟踪文件)命中时不读文件;其余工作区 / 叠加内容只读一次,同一份字节既算键又交给 fn。"""
    version = str(version)
    st = _store(snap.root, kind, version)
    key = snap.oid(path)
    if key is not None and key in st[0]:
        return _copy(st[0][key])
    data = snap.read(path)
    if data is None:
        return None
    if key is None:
        key = snapshot.blob_hash(data)
        if key in st[0]:
            return _copy(st[0][key])
    v = json.loads(json.dumps(fn(data.decode("utf-8", "replace").replace("\r\n", "\n")), ensure_ascii=False))
    st[0][key] = v
    st[1] = True
    return _copy(v)


@atexit.register
def _save():
    for (root, kind, version), (fs, dirty) in _stores.items():
        if dirty:
            try:
                nm_config.atomic_write(_file(root, kind, version),
                                       json.dumps({"kind": kind, "version": version, "facts": fs}, ensure_ascii=False, separators=(",", ":")))
            except OSError:
                pass  # 被别的进程占着(Windows)等:这次不写,下次重算
