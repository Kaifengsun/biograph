"""
Step 0: 文档下载器
=================
从 ICH / FDA / WHO 官网下载制药供应链相关的核心 PDF 文档。
支持断点续传、下载校验、手动文件登记。
"""

import os
import time
import hashlib
import json
import requests
from pathlib import Path
from typing import List, Dict, Optional

from .config import PDF_DIR, CACHE_DIR, DOCUMENT_SOURCES


class DocumentDownloader:
    """制药文档下载器"""

    def __init__(self, output_dir: Path = None):
        self.output_dir = output_dir or PDF_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.trust_env = False  # 禁用代理
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;"
                      "q=0.9,application/pdf,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        })
        self.registry_path = self.output_dir / "_document_registry.json"
        self.registry = self._load_registry()

    def _load_registry(self) -> Dict:
        """加载文档注册表"""
        if self.registry_path.exists():
            with open(self.registry_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"documents": {}}

    def _save_registry(self):
        """保存文档注册表"""
        with open(self.registry_path, 'w', encoding='utf-8') as f:
            json.dump(self.registry, f, ensure_ascii=False, indent=2)

    def _file_hash(self, filepath: Path) -> str:
        """计算文件 SHA256"""
        h = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()[:16]

    def download_pdf(self, doc_info: Dict) -> Optional[Path]:
        """下载单个 PDF"""
        doc_id = doc_info["id"]
        url = doc_info.get("url")
        title = doc_info.get("title", doc_id)

        if not url:
            print(f"  ⏭ {doc_id}: 无下载链接，需手动获取")
            return None

        filename = f"{doc_id}.pdf"
        filepath = self.output_dir / filename

        # 检查是否已下载
        if doc_id in self.registry["documents"]:
            existing = self.registry["documents"][doc_id]
            if Path(existing.get("path", "")).exists():
                print(f"  ✓ {doc_id}: 已存在 ({existing.get('size_kb', '?')} KB)")
                return Path(existing["path"])

        print(f"  ⬇ {doc_id}: 下载中...", end=" ", flush=True)
        try:
            r = self.session.get(url, timeout=60, stream=True)
            r.raise_for_status()

            # 检查是否真的是 PDF
            content_type = r.headers.get("Content-Type", "")
            if "pdf" not in content_type.lower() and not url.endswith(".pdf"):
                print(f"⚠ 非 PDF 响应 ({content_type})")

            total = int(r.headers.get("Content-Length", 0))
            downloaded = 0
            with open(filepath, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)

            # 验证文件头是否为 PDF
            with open(filepath, 'rb') as f:
                magic = f.read(5)
            if magic != b'%PDF-':
                filepath.unlink(missing_ok=True)
                print(f"✗ 下载到非 PDF 内容 (可能被网站拦截)")
                return None

            size_kb = filepath.stat().st_size / 1024
            file_hash = self._file_hash(filepath)

            # 注册
            self.registry["documents"][doc_id] = {
                "id": doc_id,
                "title": title,
                "path": str(filepath),
                "url": url,
                "size_kb": round(size_kb, 1),
                "hash": file_hash,
                "doc_type": doc_info.get("doc_type", ""),
                "authority": doc_info.get("authority", ""),
                "download_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            self._save_registry()

            print(f"✓ {size_kb:.0f} KB")
            return filepath

        except requests.exceptions.RequestException as e:
            print(f"✗ {e}")
            return None

    def register_manual_file(self, doc_id: str, filepath: str,
                              title: str = "", doc_type: str = "",
                              authority: str = ""):
        """手动注册本地文件（用于无法自动下载的文档）"""
        fp = Path(filepath)
        if not fp.exists():
            print(f"  ✗ 文件不存在: {filepath}")
            return

        size_kb = fp.stat().st_size / 1024
        file_hash = self._file_hash(fp)

        self.registry["documents"][doc_id] = {
            "id": doc_id,
            "title": title or fp.stem,
            "path": str(fp),
            "url": None,
            "size_kb": round(size_kb, 1),
            "hash": file_hash,
            "doc_type": doc_type,
            "authority": authority,
            "download_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "manual": True,
        }
        self._save_registry()
        print(f"  ✓ 已注册: {doc_id} ({size_kb:.0f} KB)")

    def download_all(self, sources: List[Dict] = None,
                     priority_filter: int = None) -> Dict[str, Path]:
        """批量下载"""
        sources = sources or DOCUMENT_SOURCES
        if priority_filter:
            sources = [s for s in sources if s.get("priority", 99) <= priority_filter]

        print(f"╔{'═' * 50}╗")
        print(f"║  制药文档下载器 — 共 {len(sources)} 个文档")
        print(f"╚{'═' * 50}╝\n")

        results = {}
        for doc in sources:
            path = self.download_pdf(doc)
            if path:
                results[doc["id"]] = path
            time.sleep(0.5)  # 礼貌间隔

        print(f"\n✅ 下载完成: {len(results)}/{len(sources)} 成功")
        return results

    def list_documents(self):
        """列出所有已注册文档"""
        docs = self.registry.get("documents", {})
        if not docs:
            print("  (无已注册文档)")
            return
        print(f"\n{'ID':<25} {'大小':>8} {'类型':<20} {'来源':<6}")
        print("-" * 70)
        for doc_id, info in docs.items():
            size = f"{info.get('size_kb', 0):.0f}KB"
            dtype = info.get('doc_type', '')[:20]
            auth = info.get('authority', '')
            exists = "✓" if Path(info.get("path", "")).exists() else "✗"
            print(f"  {exists} {doc_id:<23} {size:>8} {dtype:<20} {auth:<6}")

    def get_all_pdf_paths(self) -> List[Path]:
        """获取所有已下载的 PDF 路径"""
        paths = []
        for info in self.registry.get("documents", {}).values():
            p = Path(info.get("path", ""))
            if p.exists() and p.suffix.lower() == ".pdf":
                paths.append(p)
        return paths


def run(**kwargs):
    """Step 0 入口"""
    priority = kwargs.get("priority", 1)
    downloader = DocumentDownloader()
    results = downloader.download_all(priority_filter=priority)
    return results
