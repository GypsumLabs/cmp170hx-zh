#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 docs/ 的汉化内容发布到 GitHub Wiki 仓库。

GitHub Wiki 是一个与代码仓库分离的扁平仓库 (<owner>/<repo>.wiki.git):
    - 没有子目录: 页面名用连字符分隔, 如 start-what-is-this-card.md。
    - 通过根目录的 _Sidebar.md 控制侧边栏, _Footer.md 控制页脚。
    - 首页固定叫 Home.md。

本脚本以 mkdocs.yml 的 nav 作为权威页面顺序, 将 docs/ 下每个 .md 页面
转换为扁平 wiki 页面, 把相对 .md 链接转成 wiki 页面链接, 生成 _Sidebar.md,
然后克隆/拉取 wiki 仓库、写入全部页面并推回。

依赖: 仅 Python 标准库 (os, re, subprocess, sys, argparse)。无需第三方包。
推送时的鉴权复用系统 git 凭据 (HTTPS 凭据或 ssh)。

用法:
    python to_github_wiki.py                          # 从 git remote origin 推导 wiki 地址
    python to_github_wiki.py --repo GypsumLabs/cmp170hx-zh
    python to_github_wiki.py --wiki <本地目录或URL>   # 显式指定 wiki 仓库
    python to_github_wiki.py --dry-run                # 只生成临时目录, 不推送
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile


# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #
ROOT = os.path.dirname(os.path.abspath(__file__))
MKDOCS_YML = os.path.join(ROOT, "mkdocs.yml")
DOCS_DIR = os.path.join(ROOT, "docs")

# 页面名需要重命名的特例: 源码相对路径 -> wiki 页面名(去掉 .md)
# 例如 index.md 在 wiki 里必须叫 Home。
# 其余页面统一由 "目录-文件名" 扁平化而来, 见 page_name()。
PAGE_RENAME = {
    "index.md": "Home",
}


# --------------------------------------------------------------------------- #
# 1. 解析 mkdocs.yml 的 nav (轻量 YAML, 专门针对 nav 结构, 无第三方依赖)
# --------------------------------------------------------------------------- #
def parse_nav(text):
    """解析 mkdocs.yml 的 nav 段, 返回有序的 [(分组标题或None, 相对docs路径)] 列表。

    nav 结构:
        nav:
          - Home: index.md          # 顶层页(无分组)
          - Start here:            # 分组标题
              - start/x.md         # 组内页
              ...
    """
    lines = text.splitlines()

    # 找到 nav: 的位置
    nav_idx = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith("nav:"):
            nav_idx = i
            break
    if nav_idx is None:
        raise RuntimeError("mkdocs.yml 中找不到 nav: 段")

    entries = []          # (group, filepath) 或 (group, None) 表示分组标题
    group = None
    for ln in lines[nav_idx + 1:]:
        if not ln.strip():
            continue
        # 用缩进层级判断结构: 2 空格 = 顶层 (页/分组), 4 空格 = 组内页
        stripped = ln.lstrip()
        indent = len(ln) - len(stripped)

        if stripped.startswith("- "):
            body = stripped[2:].strip()
            # 顶层项 (缩进 0 或 2): "Home: index.md" (页) 或 "Start here:" (分组标题)
            if indent == 0 or indent == 2:
                m = re.match(r"^(.+?):\s*(.+)?$", body)
                if m and m.group(2) and m.group(2).strip().endswith(".md"):
                    # 顶层页: "Home: index.md"
                    entries.append((None, m.group(2).strip()))
                elif m:
                    # 分组标题: "Start here:"
                    group = m.group(1).strip()
                else:
                    # 顶层页 (无冒号形式): "index.md"
                    entries.append((None, body))
            # 组内页 (缩进更深, 通常 4 空格): "start/x.md"
            else:
                entries.append((group, body))

    # 去掉 group 为 None 但确实属于顶层无序列表项的潜在误判:
    # 这里 entries 已经按 (group, filepath) 记录, 足够脚本使用。
    pages = []
    for g, fp in entries:
        if fp is None:
            continue
        pages.append((g, fp))
    return pages


def load_nav_pages():
    """从 mkdocs.yml 读取权威页面清单 [(group, relpath)], 并校验文件存在。"""
    if not os.path.isfile(MKDOCS_YML):
        raise RuntimeError(f"找不到 {MKDOCS_YML}")
    with open(MKDOCS_YML, encoding="utf-8") as f:
        text = f.read()
    pages = parse_nav(text)
    if not pages:
        raise RuntimeError("nav 解析结果为空, 请检查 mkdocs.yml 格式")
    for _, fp in pages:
        full = os.path.join(DOCS_DIR, fp)
        if not os.path.isfile(full):
            raise RuntimeError(f"nav 里声明的文件不存在: {full}")
    return pages


# --------------------------------------------------------------------------- #
# 2. 页面名与链接转换
# --------------------------------------------------------------------------- #
def page_name(relpath):
    """把 docs 相对路径转成 wiki 扁平页面名(不含扩展名)。

    index.md -> Home
    start/what-is-this-card.md -> start-what-is-this-card
    """
    relpath = relpath.replace("\\", "/").lstrip("./")
    if relpath in PAGE_RENAME:
        return PAGE_RENAME[relpath]
    stem = relpath[:-3] if relpath.endswith(".md") else relpath
    return stem.replace("/", "-")


def build_flat_index(pages):
    """建立 relpath -> wiki 页面名 的映射, 用于链接转换。"""
    flat = {}
    for _, fp in pages:
        flat[fp.replace("\\", "/").lstrip("./")] = page_name(fp)
    # 兜底: 目录里未在 nav 声明的 .md 也加入(防止链接指向 nav 遗漏的文件)
    for dirpath, _, files in os.walk(DOCS_DIR):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), DOCS_DIR).replace("\\", "/")
            if rel not in flat:
                flat[rel] = page_name(rel)
    return flat


def convert_links(text, cur_dir, flat_index):
    """把文档里的相对 .md 链接转换为 wiki 扁平页面链接。

    支持形态:
        ](xxx.md)                   同目录  -> ](curdir-xxx.md)
        ](../dir/xxx.md)            跨目录  -> ](dir-xxx.md)
        ](xxx.md#anchor)            带锚点  -> ](flat.md#anchor)
    忽略外部 URL、图片、锚点专用链接。
    """
    # 只匹配 Markdown 链接/图片的目标部分 (圆括号内不含空格的形式)
    def repl(m):
        prefix = m.group(1)   # "](xxx" 里的 "](xxx" 前的文本其实在 group 外, 见下
        return prefix

    # 用两步: 先抓 "](<target>)" 形式的普通链接
    LINK_RE = re.compile(r"(\]\(|<img\s+src=\")([^)\"]+?)(\")?\)")

    def conv(m):
        before = m.group(1)
        target = m.group(2).strip()
        quote = m.group(3) or ""
        tail = m.group(0)[len(m.group(0)) - m.group(0).endswith(")") * 0:]  # 保留右括号
        # 拆分锚点
        anchor = ""
        main = target
        if "#" in target:
            main, _, anchor = target.partition("#")
            anchor = "#" + anchor
        # 拆分查询串 (基本不会出现, 稳妥起见保留)
        query = ""
        if "?" in main:
            main, _, query = main.partition("?")
            query = "?" + query

        # 非 .md 链接 (URL/图片/锚点), 原样返回
        if not main.lower().endswith(".md"):
            # 需要还原完整原始文本
            return before + target + (quote + ")" if quote else ")")

        # 规范化路径
        norm = main.replace("\\", "/")
        parts = norm.split("/")
        # 解析出从 docs 根出发的相对路径
        if norm.startswith("../"):
            # 从当前目录向上跳
            up = 0
            rest = []
            for p in parts:
                if p == "..":
                    up += 1
                else:
                    rest.append(p)
            cur_rel = cur_dir.split("/")
            # 当前文件相对 docs 的目录深度
            base = cur_rel[:-up] if up <= len(cur_rel) else []
            rel = "/".join(base + rest)
        else:
            # 同目录 (已无 . 前缀)
            rel = "/".join(cur_dir.split("/") + [norm]) if cur_dir else norm

        rel = rel.lstrip("./")
        if rel not in flat_index:
            # 找不到映射, 保守原样返回
            return before + target + (quote + ")" if quote else ")")

        flat = flat_index[rel]
        return before + flat + ".md" + anchor + query + (quote + ")" if quote else ")")

    # 匹配 "](...)" 整体 (普通链接与 ![..](..) 图片链接的目标都含 "](...)").
    LINK_RE2 = re.compile(r"\]\(([^)\s]+?)\)")
    def conv2(m):
        inner = m.group(1)
        target = inner
        anchor = ""
        main = target
        if "#" in target:
            main, _, anchor = target.partition("#")
            anchor = "#" + anchor
        query = ""
        if "?" in main:
            main, _, query = main.partition("?")
            query = "?" + query

        norm = main.replace("\\", "/")

        # 仅处理相对路径 (非 URL, 非纯锚点). 外部 URL/锚点/空 原样保留.
        if not main or main.startswith(("http://", "https://", "#", "mailto:")):
            return m.group(0)

        # 解析出从 docs 根出发的相对路径
        parts = norm.split("/")
        if norm.startswith("../"):
            up = 0
            rest = []
            for p in parts:
                if p == "..":
                    up += 1
                else:
                    rest.append(p)
            cur_rel = cur_dir.split("/")
            base = cur_rel[:-up] if up <= len(cur_rel) else []
            rel = "/".join(base + rest)
        else:
            # 同目录 (无 ./ 或 ../ 前缀)
            rel = "/".join(cur_dir.split("/") + [norm]) if cur_dir else norm
        rel = rel.lstrip("./")

        if main.lower().endswith(".md"):
            # 页面链接: 扁平化为 wiki 页面名
            if rel not in flat_index:
                return m.group(0)
            return f"]({flat_index[rel]}.md{anchor}{query})"
        else:
            # 图片等资源: 保留 docs 相对目录结构, 指向 wiki 仓库同名目录
            return f"]({rel}{anchor}{query})"

    return LINK_RE2.sub(conv2, text)


def render_page(relpath, flat_index):
    """读取 docs 下某页, 转换为 wiki 页面文本。"""
    full = os.path.join(DOCS_DIR, relpath)
    with open(full, encoding="utf-8") as f:
        text = f.read()
    cur_dir = os.path.dirname(relpath.replace("\\", "/"))
    return convert_links(text, cur_dir, flat_index)


# --------------------------------------------------------------------------- #
# 3. 生成侧边栏
# --------------------------------------------------------------------------- #
def build_sidebar(pages, flat_index):
    """生成 GitHub Wiki 的 _Sidebar.md 内容。

    分组标题用 **粗体**, 顶层页面(Home)列在最前, 组内页面用缩进列表。
    """
    # GitHub Wiki 的 _Sidebar 用嵌套无序列表 + 粗体分组标题
    result = []
    result.append("# 侧边栏")
    result.append("")
    current_group = None
    for g, fp in pages:
        flat = page_name(fp)
        if g is None:
            # 顶层页
            if current_group is not None:
                current_group = None
            result.append(f"- [{flat}]({flat}.md)")
        else:
            if current_group != g:
                result.append(f"- **{g}**")
                current_group = g
            result.append(f"  - [{flat}]({flat}.md)")
    result.append("")
    return "\n".join(result)


def build_home(flat):
    """Home 页由 index.md 转换而来。"""
    rel = "index.md"
    full = os.path.join(DOCS_DIR, rel)
    with open(full, encoding="utf-8") as f:
        text = f.read()
    return convert_links(text, "", flat)


# --------------------------------------------------------------------------- #
# 4. 生成到临时目录
# --------------------------------------------------------------------------- #
def generate(output_dir):
    """把全部 wiki 页面写入 output_dir。返回页面文件名列表。"""
    pages = load_nav_pages()
    flat = build_flat_index(pages)
    os.makedirs(output_dir, exist_ok=True)

    written = []
    # Home 页
    home = build_home(flat)
    with open(os.path.join(output_dir, "Home.md"), "w", encoding="utf-8") as f:
        f.write(home)
    written.append("Home.md")

    # 各章节页
    for g, fp in pages:
        if fp == "index.md":
            continue
        name = page_name(fp)
        text = render_page(fp, flat)
        fname = name + ".md"
        with open(os.path.join(output_dir, fname), "w", encoding="utf-8") as f:
            f.write(text)
        written.append(fname)

    # 侧边栏
    sidebar = build_sidebar(pages, flat)
    with open(os.path.join(output_dir, "_Sidebar.md"), "w", encoding="utf-8") as f:
        f.write(sidebar)
    written.append("_Sidebar.md")

    # 复制图片等资源文件 (非 .md), 保持 docs 相对目录结构
    for dirpath, _, files in os.walk(DOCS_DIR):
        for fn in files:
            if fn.endswith(".md"):
                continue
            src = os.path.join(dirpath, fn)
            rel = os.path.relpath(src, DOCS_DIR).replace("\\", "/")
            dst = os.path.join(output_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            written.append(rel)

    return written


# --------------------------------------------------------------------------- #
# 5. 克隆/更新并推送 wiki 仓库
# --------------------------------------------------------------------------- #
def git(*args, cwd=None):
    """运行 git 命令, 失败则抛出。

    统一用 UTF-8 解码输出, 避免 Windows 默认 GBK 编解码崩溃
    (git 提交信息含中文时尤其容易出现 UnicodeDecodeError)。
    """
    cmd = ["git"] + list(args)
    kwargs = dict(capture_output=True, text=True,
                  encoding="utf-8", errors="replace")
    if cwd:
        kwargs["cwd"] = cwd
    proc = subprocess.run(cmd, **kwargs)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败:\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def git_remote_origin():
    """读取当前仓库的 origin 地址。"""
    out = git("config", "--get", "remote.origin.url")
    return out


def derive_wiki_url(repo):
    """由 owner/repo 推导 wiki 的 clone 地址 (HTTPS)。"""
    repo = repo.rstrip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]
    return f"https://github.com/{repo}.wiki.git"


def main():
    parser = argparse.ArgumentParser(
        description="把 docs/ 汉化内容发布到 GitHub Wiki 仓库"
    )
    parser.add_argument("--repo", help="owner/repo, 如 GypsumLabs/cmp170hx-zh (默认从 git remote 推导)")
    parser.add_argument("--wiki", help="wiki 仓库的 clone 地址或本地目录")
    parser.add_argument("--work", help="临时工作目录(默认系统临时目录)")
    parser.add_argument("--dry-run", action="store_true", help="只生成本地文件, 不克隆不推送")
    parser.add_argument("--out", help="配合 --dry-run: 把生成的页面写入该目录(默认打印到临时目录)")
    args = parser.parse_args()

    # 确定 wiki 仓库地址
    wiki_url = None
    if args.wiki and ("/" in args.wiki or os.path.isdir(args.wiki)):
        # 可能是本地目录或 URL
        if os.path.isdir(args.wiki) and not args.wiki.startswith("http"):
            wiki_url = os.path.abspath(args.wiki)
        else:
            wiki_url = args.wiki
    elif args.repo:
        wiki_url = derive_wiki_url(args.repo)
    else:
        origin = git_remote_origin()
        # origin 形如 https://github.com/GypsumLabs/cmp170hx-zh.git
        m = re.match(r"https?://github\.com/([^/]+/[^/]+?)(?:\.git)?$", origin)
        if m:
            wiki_url = derive_wiki_url(m.group(1))
        else:
            raise RuntimeError("无法从 origin 推导 wiki 地址, 请用 --repo 或 --wiki 指定")

    print(f"[1/4] 解析 mkdocs.yml 导航...")
    pages = load_nav_pages()
    print(f"      共 {len(pages)} 个页面")

    if args.dry_run:
        out = args.out or tempfile.mkdtemp(prefix="cmp-wiki-")
        written = generate(out)
        print(f"[2/4] 已在 {out} 生成 {len(written)} 个 wiki 页面 (dry-run, 未推送)")
        for w in sorted(written):
            print(f"      - {w}")
        return

    # 工作目录
    work = args.work or tempfile.mkdtemp(prefix="cmp-wiki-")
    clone_dir = os.path.join(work, "wiki")

    print(f"[2/4] 克隆 wiki 仓库: {wiki_url}")
    if not os.path.isdir(clone_dir):
        git("clone", wiki_url, clone_dir)
    else:
        git("pull", "--ff-only", cwd=clone_dir)

    # 清理旧内容 (保留 .git 和 _Footer.md, 删除所有 .md 页面与图片目录, 重新生成)
    print(f"[3/4] 清理旧页面并生成新页面")
    for fn in os.listdir(clone_dir):
        if fn in (".git", "_Footer.md", ".gitignore"):
            continue
        full = os.path.join(clone_dir, fn)
        if os.path.isdir(full):
            shutil.rmtree(full, ignore_errors=True)
        else:
            os.remove(full)

    written = generate(clone_dir)

    # 提交并推送
    print(f"[4/4] 提交并推送 {len(written)} 个页面")
    git("add", "-A", cwd=clone_dir)
    try:
        git("commit", "-m", "同步 docs/ 汉化内容到 wiki", cwd=clone_dir)
    except RuntimeError:
        print("      无内容变化, 跳过提交")
    else:
        git("push", cwd=clone_dir)
        print(f"      已推送 {len(written)} 个页面到 wiki")

    # 清理工作目录 (可选)
    if not args.work:
        shutil.rmtree(work, ignore_errors=True)
    print("完成。")


if __name__ == "__main__":
    main()
