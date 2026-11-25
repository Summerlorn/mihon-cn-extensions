#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跟随 keiyoushi 官方仓库同步本扩展源。

做什么：
  1. 拉上游 index.pb（keiyoushi/extensions 的 repo 分支）
  2. 只保留 packages.txt 里列出的扩展
  3. 站点只保留 domains.txt 里实测可直连的域名
  4. 有新版本就下载新 APK、缺图标就补图标
  5. 重写 index.min.json，删掉被替换的旧 APK
  6. --purge-only 时只清 jsDelivr 缓存

用法：
  python sync.py               正常同步
  python sync.py --dry-run     只报告会变什么，不写文件
  python sync.py --purge-only  只清 jsDelivr 缓存

环境变量（GitHub Actions 自动注入）：
  GITHUB_REPOSITORY   owner/repo，用于清缓存；本地跑可不管
"""
import gzip
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.request
import zipfile
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(ROOT, 'index.min.json')
REPO_JSON = os.path.join(ROOT, 'repo.json')
APK_DIR = os.path.join(ROOT, 'apk')
ICON_DIR = os.path.join(ROOT, 'icon')
PKG_FILE = os.path.join(ROOT, 'packages.txt')
DOMAIN_FILE = os.path.join(ROOT, 'domains.txt')

UPSTREAM = [
    'https://raw.githubusercontent.com/keiyoushi/extensions/repo/index.pb',
    'https://fastly.jsdelivr.net/gh/keiyoushi/extensions@repo/index.pb',
    'https://github.com/keiyoushi/extensions/raw/repo/index.pb',
]
UA = 'mihon-cn-repo-sync/1.0 (+https://github.com/keiyoushi/extensions)'
SSL_CTX = ssl.create_default_context()
SSL_CTX_NOCHECK = ssl._create_unverified_context()   # 仅用于证书链有问题的环境


# ---------------- 网络 ----------------
def fetch(url, retries=3, timeout=60):
    """先走 curl，再退回 urllib。

    国内网络下 Python 自带 TLS 的握手很容易被重置（curl 用系统 schannel 反而能过），
    所以 curl 优先；GitHub Actions 的 runner 上两者都正常，不受影响。
    """
    last = None
    for i in range(retries):
        for cmd in (['curl', '-fsSL', '--ssl-no-revoke', '--max-time', str(timeout), '-A', UA, url],
                    ['curl', '-fsSL', '--max-time', str(timeout), '-A', UA, url]):
            try:
                p = subprocess.run(cmd, capture_output=True, timeout=timeout + 30)
                if p.returncode == 0 and p.stdout:
                    return p.stdout
                last = (p.stderr or b'').decode('utf8', 'replace').strip()[:200] or f'curl rc={p.returncode}'
            except FileNotFoundError:
                break
            except Exception as e:
                last = e
        for ctx in (SSL_CTX, SSL_CTX_NOCHECK):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': UA})
                with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                    return r.read()
            except Exception as e:            # 证书吊销/链问题换不校验上下文再试
                last = e
        time.sleep(2 + i * 3)
    raise RuntimeError(f'下载失败 {url}: {last}')


def download_to(url, dest):
    data = fetch(url, timeout=180)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + '.part'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, dest)
    return len(data)


def purge():
    """清 jsDelivr 缓存。

    注意：purge 接口对 @main 这种分支别名并不保证立刻生效（实测 fastly 节点
    会继续返回旧内容直到 12 小时的 s-maxage 过期）。所以这里只尽力而为地多
    试几轮，真正的兜底是"索引里引用的 APK 都还在"——见下面的保留策略。
    """
    repo = os.environ.get('GITHUB_REPOSITORY', '')
    if not repo:
        print('· 没有 GITHUB_REPOSITORY，跳过清缓存')
        return
    for path in ('index.min.json', 'repo.json'):
        url = f'https://purge.jsdelivr.net/gh/{repo}@main/{path}'
        for attempt in range(3):
            try:
                body = fetch(url, retries=1, timeout=30)
                state = 'finished'
                try:
                    state = json.loads(body).get('status', state)
                except Exception:
                    pass
                print(f'· 已清缓存 {path}（{state}，第 {attempt + 1} 轮）')
                break
            except Exception as e:
                print(f'· 清缓存失败 {path} 第 {attempt + 1} 轮: {e}')
                time.sleep(20)


# ---------------- protobuf ----------------
def rv(b, i):
    r = s = 0
    while True:
        x = b[i]
        i += 1
        r |= (x & 0x7f) << s
        s += 7
        if not x & 0x80:
            return r, i


def fields(b):
    i = 0
    out = []
    while i < len(b):
        k, i = rv(b, i)
        f, w = k >> 3, k & 7
        if w == 0:
            v, i = rv(b, i)
            out.append((f, 0, v))
        elif w == 2:
            l, i = rv(b, i)
            v = b[i:i + l]
            i += l
            out.append((f, 2, v))
        elif w == 5:
            out.append((f, 5, b[i:i + 4]))
            i += 4
        elif w == 1:
            out.append((f, 1, b[i:i + 8]))
            i += 8
        else:
            raise ValueError(f'未知 wire type {w}')
    return out


def parse_upstream(raw):
    d = raw
    if d[:2] == b'\x1f\x8b':
        d = gzip.decompress(d)
    top = fields(d)
    fingerprint = next((v.decode() for f, t, v in top if f == 3 and t == 2), None)
    payload = [v for f, t, v in top if f == 101][0]
    exts = {}
    for eb in [v for f, t, v in fields(payload) if f == 1]:
        o = {'sources': []}
        for f, t, v in fields(eb):
            if f == 1 and t == 2:
                o['name'] = v.decode('utf8', 'replace')
            elif f == 2 and t == 2:
                o['pkg'] = v.decode('utf8', 'replace')
            elif f == 3 and t == 2:
                sub = {sf: sv for sf, st, sv in fields(v) if st == 2}
                o['apk_url'] = sub.get(1, b'').decode('utf8', 'replace')
                o['icon_url'] = sub.get(2, b'').decode('utf8', 'replace')
            elif f == 5 and t == 0:
                o['code'] = v
            elif f == 6 and t == 2:
                o['version'] = v.decode('utf8', 'replace')
            elif f == 7 and t == 0:
                o['nsfw'] = v
            elif f == 8 and t == 2:
                s = {}
                for sf, st, sv in fields(v):
                    if st == 2:
                        s[{2: 'name', 3: 'lang', 4: 'url'}.get(sf, f'x{sf}')] = sv.decode('utf8', 'replace')
                    elif sf == 1:
                        s['id'] = sv
                o['sources'].append(s)
        if o.get('pkg'):
            exts[o['pkg']] = o
    return exts, fingerprint


# ---------------- 工具 ----------------
def read_lines(path):
    if not os.path.exists(path):
        return []
    return [l.strip() for l in open(path, encoding='utf-8') if l.strip() and not l.startswith('#')]


def host_of(u):
    try:
        return (urlparse(u).hostname or '').lower()
    except Exception:
        return ''


def fix_version(v):
    # Mihon 会做 version.substringBeforeLast('.').toDouble()，必须是 x.y.z
    return v if v.count('.') >= 2 else v + '.0'


def valid_apk(path):
    try:
        with zipfile.ZipFile(path) as z:
            return 'AndroidManifest.xml' in z.namelist()
    except Exception:
        return False


# ---------------- 主流程 ----------------
def main():
    dry = '--dry-run' in sys.argv

    local = json.load(open(INDEX, encoding='utf-8'))
    local_by_pkg = {e['pkg']: e for e in local}
    order = [e['pkg'] for e in local]
    allow = set(read_lines(PKG_FILE)) or set(local_by_pkg)
    domains = {d.lower() for d in read_lines(DOMAIN_FILE)}

    print(f'本地 {len(local)} 个扩展，白名单 {len(allow)} 个，可用域名 {len(domains)} 个')

    raw, src = None, None
    for u in UPSTREAM:
        try:
            raw = fetch(u, timeout=120)
            src = u
            break
        except Exception as e:
            print(f'  取上游失败 {urlparse(u).hostname}: {e}')
    if raw is None:
        print('所有上游地址都失败，退出')
        return 1
    print(f'上游索引 {len(raw)} 字节（来源 {urlparse(src).hostname}）')

    up, fingerprint = parse_upstream(raw)
    print(f'上游共 {len(up)} 个扩展')

    changed, added, skipped = [], [], []
    new_index = []

    for pkg in order:
        old = local_by_pkg[pkg]
        u = up.get(pkg)
        if not u:
            skipped.append((old['name'], '上游已下架，保留现有版本'))
            new_index.append(old)
            continue

        # 站点按白名单过滤
        srcs = []
        for s in u['sources']:
            url = s.get('url') or ''
            if not url or not (s.get('lang') or '').startswith('zh'):
                continue
            if domains and host_of(url) not in domains:
                continue
            srcs.append({
                'id': int(s.get('id') or 0),
                'lang': s.get('lang') or 'zh',
                'name': s.get('name') or '',
                'baseUrl': url,
            })
        if not srcs:
            skipped.append((old['name'], '新版站点全不在可直连白名单，保留旧条目'))
            new_index.append(old)
            continue

        apk_name = (u.get('apk_url') or '').rsplit('/', 1)[-1]
        if not apk_name:
            skipped.append((old['name'], '上游没给 APK 地址'))
            new_index.append(old)
            continue

        entry = {
            'name': u['name'],
            'pkg': pkg,
            'apk': apk_name,
            'lang': (u['sources'][0].get('lang') or 'zh') if u['sources'] else 'zh',
            'code': int(u['code']),
            'version': fix_version(u['version']),
            'nsfw': 1 if u.get('nsfw', 0) >= 3 else 0,
            'sources': srcs,
        }
        new_index.append(entry)

        # 需要下载 APK 的条件：版本变了，或文件缺失/损坏
        apk_path = os.path.join(APK_DIR, apk_name)
        need_apk = entry['code'] > old['code'] or not valid_apk(apk_path)
        if need_apk:
            if dry:
                changed.append((entry['name'], old['version'], entry['version'], '将下载'))
            else:
                n = download_to(u['apk_url'], apk_path)
                if not valid_apk(apk_path):
                    skipped.append((entry['name'], f'下载的 APK 校验失败（{n} 字节）'))
                    new_index[-1] = old
                    continue
                changed.append((entry['name'], old['version'], entry['version'], f'{n // 1024} KB'))

        # 图标补齐
        icon_path = os.path.join(ICON_DIR, f'{pkg}.png')
        if u.get('icon_url') and (not os.path.exists(icon_path) or os.path.getsize(icon_path) < 500):
            if not dry:
                try:
                    download_to(u['icon_url'].replace('https://cdn.jsdelivr.net/', 'https://fastly.jsdelivr.net/'), icon_path)
                except Exception as e:
                    print(f'  图标下载失败 {pkg}: {e}')
        elif u.get('icon_url'):
            pass  # 已有图标就不动，避免每次同步都改二进制

    # 白名单里有、但本地没有的新包
    for pkg in sorted(allow - set(order)):
        u = up.get(pkg)
        if not u:
            continue
        added.append(pkg)

    new_index.sort(key=lambda e: order.index(e['pkg']) if e['pkg'] in order else 999)

    print('\n===== 结果 =====')
    if changed:
        for n, a, b, note in changed:
            print(f'  更新 {n:28} {a} -> {b}  ({note})')
    else:
        print('  没有需要更新的扩展')
    if skipped:
        for n, why in skipped:
            print(f'  跳过 {n:28} {why}')
    if added:
        print('  白名单里但尚未收录:', added)

    if dry:
        print('\n（--dry-run，未写入任何文件）')
        return 0

    # 清理旧 APK：每个包只保留"当前版本 + 上一个版本"。
    # 保留上一个版本是有意为之——jsDelivr 对 @main 有 12 小时缓存，
    # 期间手机端读到的仍是旧索引，旧索引指向的就是上一个版本的文件名。
    # 若立刻删掉，这段时间里装/更新这些扩展会 404。
    keep = {e['apk'] for e in new_index}
    removed = 0
    if os.path.isdir(APK_DIR):
        groups = {}
        for f in os.listdir(APK_DIR):
            if not f.endswith('.apk'):
                continue
            m = re.match(r'^(.*)-v(\d+(?:\.\d+)*)\.apk$', f)
            if not m:                      # 认不出格式的，一律不动
                continue
            key, ver = m.group(1), tuple(int(x) for x in m.group(2).split('.'))
            groups.setdefault(key, []).append((ver, f))
        for key, items in groups.items():
            items.sort(reverse=True)       # 版本号从大到小
            referenced = [f for _, f in items if f in keep]
            spare = [f for _, f in items if f not in keep]
            for f in spare[1:]:            # 未被引用的，只留最新的一个
                os.remove(os.path.join(APK_DIR, f))
                removed += 1
    if removed:
        print(f'  清理过旧的 APK: {removed} 个（每个包保留当前版本 + 上一个版本）')

    old_text = open(INDEX, encoding='utf-8').read() if os.path.exists(INDEX) else ''
    new_text = json.dumps(new_index, ensure_ascii=False, indent=1)
    if new_text != old_text:
        open(INDEX, 'w', encoding='utf-8', newline='\n').write(new_text)
        print('  index.min.json 已更新')
    else:
        print('  index.min.json 无变化')

    # 签名指纹同步（一般不会变，变了说明上游换了签名，属于重大变更）
    if fingerprint:
        meta = json.load(open(REPO_JSON, encoding='utf-8'))
        if meta['meta'].get('signingKeyFingerprint') != fingerprint:
            meta['meta']['signingKeyFingerprint'] = fingerprint
            json.dump(meta, open(REPO_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
            print('  !! 上游签名指纹变了，已更新 repo.json')

    print(f'  当前共 {len(new_index)} 个扩展，APK 目录 {len(os.listdir(APK_DIR))} 个文件')
    return 0


if __name__ == '__main__':
    if '--purge-only' in sys.argv:
        purge()
        sys.exit(0)
    sys.exit(main())
