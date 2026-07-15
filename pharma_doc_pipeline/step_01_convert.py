"""
Step 1: PDF → Markdown 转换
============================
后端选择:
  - MinerU (magic-pdf): 全自动数字 PDF 转换，带版面分析
  - raw_markdown: 轻量回退，用 pymupdf4llm 直接抽文本
"""

import json
import time
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from .config import (PDF_DIR, MD_DIR, CACHE_DIR, PipelineSettings)


# ─────────────────── 工具函数 ───────────────────

def _check_mineru_available() -> bool:
    """检查 MinerU (magic-pdf) 是否可用"""
    try:
        import magic_pdf  # noqa: F401
        return True
    except ImportError:
        return False


def _check_pymupdf4llm_available() -> bool:
    try:
        import pymupdf4llm  # noqa: F401
        return True
    except ImportError:
        return False


# ─────────────────── MinerU 后端 ───────────────────

def convert_with_mineru(pdf_path: Path, output_dir: Path,
                        device: str = "cuda") -> Optional[Path]:
    """
    使用 MinerU 将 PDF 转为 Markdown。
    MinerU 输出结构: output_dir/<stem>/<stem>.md + images/
    返回生成的 .md 文件路径
    """
    stem = pdf_path.stem
    doc_output = output_dir / stem
    md_file = doc_output / f"{stem}.md"

    if md_file.exists():
        print(f"    ✓ 已存在: {md_file.name}")
        return md_file

    try:
        # 方式一: 用 Python API (MinerU 1.3.x)
        from magic_pdf.data.data_reader_writer import FileBasedDataWriter, FileBasedDataReader
        from magic_pdf.data.dataset import PymuDocDataset
        from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze

        # 读取 PDF
        reader = FileBasedDataReader("")
        pdf_bytes = reader.read(str(pdf_path))

        # 创建 Dataset，自动分类 (文本 PDF vs 扫描件)
        ds = PymuDocDataset(pdf_bytes)
        parse_method = ds.classify()
        is_ocr = str(parse_method).lower().endswith("ocr")
        print(f"    → 检测类型: {'OCR(扫描件)' if is_ocr else 'TXT(文本PDF)'}")

        # 确保输出目录存在
        doc_output.mkdir(parents=True, exist_ok=True)
        img_dir = doc_output / "images"
        img_dir.mkdir(exist_ok=True)

        img_writer = FileBasedDataWriter(str(img_dir))

        # 模型推理
        infer_result = ds.apply(doc_analyze, ocr=is_ocr)

        # 管道处理: 根据分类结果选择 txt 或 ocr pipeline
        if is_ocr:
            pipe_result = infer_result.pipe_ocr_mode(img_writer)
        else:
            pipe_result = infer_result.pipe_txt_mode(img_writer)

        # 输出 Markdown (参数是图片目录的相对路径前缀)
        md_content = pipe_result.get_markdown("images")

        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_content)

        print(f"    ✓ MinerU: {md_file.name} ({len(md_content)} chars)")
        return md_file

    except ImportError:
        # 方式二: 用命令行
        print(f"    → MinerU API 不可用，尝试命令行...")
        return _convert_mineru_cli(pdf_path, output_dir, device)
    except Exception as e:
        print(f"    ✗ MinerU 错误: {e}")
        return None


def _convert_mineru_cli(pdf_path: Path, output_dir: Path,
                        device: str = "cuda") -> Optional[Path]:
    """MinerU 命令行回退"""
    stem = pdf_path.stem
    doc_output = output_dir / stem
    md_file = doc_output / f"{stem}.md"

    try:
        cmd = [
            "magic-pdf", "-p", str(pdf_path),
            "-o", str(output_dir),
            "-m", "auto",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and md_file.exists():
            print(f"    ✓ MinerU CLI: {md_file.name}")
            return md_file
        else:
            print(f"    ✗ MinerU CLI 失败: {result.stderr[:200]}")
            return None
    except FileNotFoundError:
        print("    ✗ magic-pdf 命令未找到，请安装: pip install magic-pdf[full]")
        return None
    except subprocess.TimeoutExpired:
        print("    ✗ MinerU 超时 (>300s)")
        return None


# ─────────────────── pymupdf4llm 后端 (轻量回退) ───────────────────

def convert_with_pymupdf4llm(pdf_path: Path, output_dir: Path) -> Optional[Path]:
    """
    使用 pymupdf4llm 直接提取 Markdown (纯文本 + 标题检测)。
    不需要 GPU，速度快，但版面分析不如 MinerU。
    适合数字原生 PDF (ICH/FDA/WHO 官方文档)。
    """
    stem = pdf_path.stem
    doc_output = output_dir / stem
    doc_output.mkdir(parents=True, exist_ok=True)
    md_file = doc_output / f"{stem}.md"

    if md_file.exists():
        print(f"    ✓ 已存在: {md_file.name}")
        return md_file

    try:
        import pymupdf4llm

        md_text = pymupdf4llm.to_markdown(str(pdf_path))

        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_text)

        print(f"    ✓ pymupdf4llm: {md_file.name} ({len(md_text)} chars)")
        return md_file

    except ImportError:
        print("    ✗ pymupdf4llm 未安装: pip install pymupdf4llm")
        return None
    except Exception as e:
        print(f"    ✗ pymupdf4llm 错误: {e}")
        return None


# ─────────────────── 纯 PyMuPDF 回退 ───────────────────

def convert_with_pymupdf_raw(pdf_path: Path, output_dir: Path) -> Optional[Path]:
    """
    最轻量回退: 用 PyMuPDF 直接逐页提取文本。
    不做版面分析，但保证能跑。
    """
    stem = pdf_path.stem
    doc_output = output_dir / stem
    doc_output.mkdir(parents=True, exist_ok=True)
    md_file = doc_output / f"{stem}.md"

    if md_file.exists():
        print(f"    ✓ 已存在: {md_file.name}")
        return md_file

    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(pdf_path))
        lines = []
        for page_num, page in enumerate(doc, 1):
            text = page.get_text("text")
            if text.strip():
                lines.append(f"\n<!-- Page {page_num} -->\n")
                lines.append(text)
        doc.close()

        md_text = "\n".join(lines)

        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(md_text)

        print(f"    ✓ PyMuPDF raw: {md_file.name} ({len(md_text)} chars)")
        return md_file

    except ImportError:
        print("    ✗ PyMuPDF 未安装: pip install PyMuPDF")
        return None
    except Exception as e:
        print(f"    ✗ PyMuPDF 错误: {e}")
        return None


# ─────────────────── 统一转换入口 ───────────────────

class PDFConverter:
    """统一 PDF→Markdown 转换器"""

    BACKENDS = {
        "mineru": convert_with_mineru,
        "pymupdf4llm": convert_with_pymupdf4llm,
        "raw": convert_with_pymupdf_raw,
    }

    # 回退链
    FALLBACK_CHAIN = ["mineru", "pymupdf4llm", "raw"]

    def __init__(self, settings: PipelineSettings = None):
        self.settings = settings or PipelineSettings()
        self.output_dir = MD_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 转换结果记录
        self.results_path = CACHE_DIR / "conversion_results.json"
        self.results = self._load_results()

    def _load_results(self) -> Dict:
        if self.results_path.exists():
            with open(self.results_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_results(self):
        with open(self.results_path, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)

    def convert_one(self, pdf_path: Path) -> Optional[Path]:
        """转换单个 PDF，按回退链尝试"""
        stem = pdf_path.stem

        # 已经转换过
        if stem in self.results:
            existing_md = Path(self.results[stem].get("md_path", ""))
            if existing_md.exists():
                return existing_md

        preferred = self.settings.parser.backend
        chain = [preferred] + [b for b in self.FALLBACK_CHAIN if b != preferred]

        for backend_name in chain:
            fn = self.BACKENDS.get(backend_name)
            if fn is None:
                continue

            kwargs = {"pdf_path": pdf_path, "output_dir": self.output_dir}
            if backend_name == "mineru":
                kwargs["device"] = self.settings.parser.mineru_device

            md_path = fn(**kwargs)
            if md_path and md_path.exists():
                self.results[stem] = {
                    "pdf_path": str(pdf_path),
                    "md_path": str(md_path),
                    "backend": backend_name,
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "chars": md_path.stat().st_size,
                }
                self._save_results()
                return md_path

        print(f"    ✗ 所有后端均失败: {pdf_path.name}")
        return None

    def convert_all(self, pdf_paths: List[Path] = None) -> Dict[str, Path]:
        """批量转换"""
        if pdf_paths is None:
            pdf_paths = sorted(PDF_DIR.glob("*.pdf"))

        if not pdf_paths:
            print("  ⚠ 无 PDF 文件可转换")
            return {}

        print(f"╔{'═' * 50}╗")
        print(f"║  PDF → Markdown 转换 — 共 {len(pdf_paths)} 个文件")
        print(f"║  首选后端: {self.settings.parser.backend}")
        print(f"╚{'═' * 50}╝\n")

        results = {}
        for pdf_path in pdf_paths:
            print(f"  [{pdf_paths.index(pdf_path)+1}/{len(pdf_paths)}] {pdf_path.name}")
            md_path = self.convert_one(pdf_path)
            if md_path:
                results[pdf_path.stem] = md_path

        print(f"\n✅ 转换完成: {len(results)}/{len(pdf_paths)} 成功")
        return results


def run(**kwargs) -> Dict[str, Path]:
    """Step 1 入口"""
    settings = kwargs.get("settings", PipelineSettings())
    converter = PDFConverter(settings=settings)
    pdf_paths = kwargs.get("pdf_paths")
    return converter.convert_all(pdf_paths=pdf_paths)
