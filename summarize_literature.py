import os
from pathlib import Path
from openai import OpenAI
MOONSHOT_BASE_URL = os.getenv("MOONSHOT_API_BASE_URL", "https://api.moonshot.cn/v1")
MOONSHOT_API_KEY = os.getenv("MOONSHOT_API_KEY", "")
MOONSHOT_MODEL = os.getenv("MOONSHOT_MODEL", "kimi-k2.6")

def summarize_paper(file_path: Path, text: str, client: OpenAI, model: str) -> str:
    prompt = f"""
    You are an expert academic researcher summarizing a paper for a master's thesis literature review. 
    The thesis focuses on: "Enhancing Dynamic Capabilities in Pharmaceutical Supply Chain Risk Control via GraphRAG and Agent-Based Simulation" 
    under the theoretical framework of Prof. Stylianos Kavadias and Nektarios Oraiopoulos (Dynamic Capabilities, Ambiguity, Path Dependence, De-risking).

    Below is the extracted markdown text (beginning parts) of a research paper:
    ---
    {text}
    ---
    
    Extract and format the following information in Chinese (except names/titles):
    1. **Title**: The exact paper title
    2. **Authors/Year**: (If discernible from the text, otherwise write 'N/A')
    3. **Core Theme**: (What is the main topic of this paper? e.g., Supply chain resilience, GraphRAG, etc.)
    4. **Methodology/Contribution**: (How did they solve it? What is their main claim?)
    5. **Project Relevance**: (How does this paper specifically support our thesis? Give a 1-2 sentence instruction on where we should cite this in our RP, such as "Cite this in the GraphRAG section to show X" or "Cite this in the theoretical background to support Ambiguity")
    
    Make it concise and highly academic. Output ONLY the numbered list.
    """
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=800
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error summarizing {file_path.name}: {e}"

def main():
    client = OpenAI(api_key=MOONSHOT_API_KEY, base_url=MOONSHOT_BASE_URL)
    
    md_dir = Path("文献/processed_md")
    output_file = Path("文献/Literature_Notes.md")
    
    if not md_dir.exists():
        print("Markdown folder not found!")
        return
        
    md_files = list(md_dir.rglob("*.md"))
    print(f"Found {len(md_files)} markdown files to summarize.")
    
    with open(output_file, 'w', encoding='utf-8') as out_f:
        out_f.write("# 文献阅读笔记与引用追踪清单\n\n")
        out_f.write("> 自动生成用于 RP 和最终 Thesis 的参考文献索引。每篇文献与我们的『医药供应链 GraphRAG 与智能体仿真』课题的结合点已提炼完毕。\n\n")
        out_f.write("---\n\n")
        
        for idx, md_path in enumerate(md_files, 1):
            print(f"Processing [{idx}/{len(md_files)}]: {md_path.parent.name} ...")
            try:
                with open(md_path, 'r', encoding='utf-8') as f:
                    content = f.read(6000)  # Read up to 6000 chars (usually abstract + intro)
                    
                summary = summarize_paper(md_path, content, client, MOONSHOT_MODEL)
                out_f.write(f"## {idx}. {md_path.parent.name}\n")
                out_f.write(summary + "\n\n---\n\n")
                print("  -> Done.")
            except Exception as e:
                print(f"  -> Failed: {e}")

if __name__ == "__main__":
    main()
