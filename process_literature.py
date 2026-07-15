import os
import re
import shutil
from pathlib import Path
from openai import OpenAI

# 导入项目中原本配置好的 LLM 密钥和配置
MOONSHOT_BASE_URL = os.getenv("MOONSHOT_API_BASE_URL", "https://api.moonshot.cn/v1")
MOONSHOT_API_KEY = os.getenv("MOONSHOT_API_KEY", "")
MOONSHOT_MODEL = os.getenv("MOONSHOT_MODEL", "kimi-k2.6")
from pharma_doc_pipeline.step_01_convert import convert_with_mineru, convert_with_pymupdf4llm, convert_with_pymupdf_raw

def clean_filename(filename: str) -> str:
    """清理文件名中的不合法字符"""
    invalid_chars = r'[<>:"/\\|?*]'
    clean = re.sub(invalid_chars, '_', filename)
    clean = clean.replace('\n', ' ').strip()
    return clean[:100]  # 防止文件名过长

def extract_title_with_llm(md_text: str) -> str:
    """使用 Kimi 提取论文官方标题"""
    client = OpenAI(api_key=MOONSHOT_API_KEY, base_url=MOONSHOT_BASE_URL)
    
    prompt = (
        "You are an academic assistant. Extract the exact OFFICIAL academic title of the paper "
        "from the following markdown text (which is the beginning of the paper). \n"
        "Output ONLY the exact title, without quotes, without introductory text, and without "
        "any extra explanation.\n\n"
        f"Text:\n{md_text[:3000]}"
    )
    
    try:
        response = client.chat.completions.create(
            model=MOONSHOT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=100
        )
        title = response.choices[0].message.content.strip().strip('"').strip("'")
        return clean_filename(title)
    except Exception as e:
        print(f"    - LLM 提取标题失败: {e}")
        return "Unknown_Title"

def process_docx(docx_path: Path, output_md_path: Path):
    """简单提取 DOCX 文本并存为 MD"""
    try:
        import docx
        doc = docx.Document(docx_path)
        text = "\n\n".join([para.text for para in doc.paragraphs if para.text.strip()])
        with open(output_md_path, 'w', encoding='utf-8') as f:
            f.write(text)
        return True
    except Exception as e:
        print(f"    - DOCX解析失败 (可能是未安装 python-docx): {e}")
        return False

def main():
    lit_dir = Path("文献")
    out_dir = lit_dir / "processed_md"
    out_dir.mkdir(exist_ok=True)
    
    files = list(lit_dir.glob("*.pdf")) + list(lit_dir.glob("*.docx"))
    if not files:
        print("没有找到需要处理的文件。")
        return
        
    print(f"正在处理 {len(files)} 个文献文件...")
    
    for file_path in files:
        print(f"\n[{file_path.name}]")
        
        md_file = None
        current_out_dir = out_dir / file_path.stem
        current_out_dir.mkdir(exist_ok=True)
        
        # 1. 转换为 Markdown
        if file_path.suffix.lower() == ".pdf":
            print("  - 尝试 MinerU 转换...")
            # MinerU 需要的 output_dir 会在其下面建 stem 文件夹
            md_file = convert_with_mineru(file_path, out_dir, device="cuda")
            if not md_file:
                print("  - MinerU 失败，尝试 PyMuPDF4LLM...")
                md_file = convert_with_pymupdf4llm(file_path, out_dir)
            if not md_file:
                print("  - PyMuPDF4LLM 失败，尝试 RAW PyMuPDF...")
                md_file = convert_with_pymupdf_raw(file_path, out_dir)
        elif file_path.suffix.lower() == ".docx":
            print("  - 尝试 DOCX 文本抽取...")
            md_file = current_out_dir / f"{file_path.stem}.md"
            if not process_docx(file_path, md_file):
                md_file = None
                
        if not md_file or not md_file.exists():
            print("  ❌ 转换失败，跳过。")
            continue
            
        # 2. 读取开头的 Markdown 内容
        with open(md_file, 'r', encoding='utf-8') as f:
            md_text = f.read(4000)
            
        if not md_text.strip():
            print("  ❌ Markdown 内容为空，跳过。")
            continue
            
        # 3. 让大模型提取论文标题
        print("  - 调用 LLM 提取准确标题...")
        title = extract_title_with_llm(md_text)
        print(f"  - 识别到标题: 【{title}】")
        
        if title and title != "Unknown_Title" and title != clean_filename(file_path.stem):
            # 4. 重命名原始文件和生成的MD文件及文件夹
            new_orig_name = f"{title}{file_path.suffix}"
            new_orig_path = lit_dir / new_orig_name
            
            # 如果新名字已存在，加个标号
            counter = 1
            while new_orig_path.exists() and new_orig_path != file_path:
                new_orig_path = lit_dir / f"{title}_{counter}{file_path.suffix}"
                counter += 1
                
            if new_orig_path != file_path:
                try:
                    # 重命名原文件
                    file_path.rename(new_orig_path)
                    print(f"  ✅ 原文件已重命名为 -> {new_orig_path.name}")
                    
                    # 重命名 MD 所在的文件夹
                    new_md_dir = out_dir / new_orig_path.stem
                    if current_out_dir.exists() and not new_md_dir.exists():
                        current_out_dir.rename(new_md_dir)
                        # 重命名内部的 MD 文件
                        old_md_in_new_dir = new_md_dir / md_file.name
                        new_md_in_new_dir = new_md_dir / f"{new_orig_path.stem}.md"
                        if old_md_in_new_dir.exists():
                            old_md_in_new_dir.rename(new_md_in_new_dir)
                    print(f"  ✅ MD 结果文件夹也已重命名")
                except Exception as e:
                    print(f"  ⚠ 重命名时出错: {e}")
        else:
            print("  - 标题无需重命名或提取失败。")
            
    print("\n🎉 所有文献处理完毕！")

if __name__ == "__main__":
    main()
