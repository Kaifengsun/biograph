"""
DeepSeek LLM 客户端
"""

import requests
from typing import List, Dict, Optional
from .config import LLMConfig


class DeepSeekClient:
    """DeepSeek API 客户端，带重试和缓存"""

    def __init__(self, config: LLMConfig = None):
        self.config = config or LLMConfig()
        self._session = None

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            self._session.trust_env = False  # 禁用代理
            self._session.headers.update({
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            })
        return self._session

    def chat(self, messages: List[Dict[str, str]],
             temperature: float = None,
             max_tokens: int = None) -> str:
        """
        调用 DeepSeek chat completion API。
        返回助手回复文本。
        """
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature or self.config.temperature,
            "max_tokens": max_tokens or self.config.max_tokens,
        }

        for attempt in range(3):
            try:
                resp = self.session.post(
                    f"{self.config.api_base_url}/chat/completions",
                    json=payload,
                    timeout=self.config.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                if attempt == 2:
                    print(f"  ⚠ LLM API 失败 (3次重试后): {e}")
                    return f"[LLM Error: {e}]"
                import time
                time.sleep(2 ** attempt)

    def generate_answer(self, query: str, context: str,
                        system_prompt: str = None) -> str:
        """
        基于检索上下文生成回答。

        Args:
            query: 用户问题
            context: GraphRAG 检索到的上下文（chunks + KG facts）
            system_prompt: 可选的系统提示

        Returns:
            LLM 生成的回答
        """
        if system_prompt is None:
            system_prompt = GRAPHRAG_SYSTEM_PROMPT

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"## 检索上下文\n\n{context}\n\n## 用户问题\n\n{query}"},
        ]
        return self.chat(messages)

    def extract_entities(self, query: str) -> List[str]:
        """
        从用户问题中提取可能的实体关键词（药名、API名、厂商名等）。
        用于 Stage 1 → Stage 2 桥接。
        """
        messages = [
            {"role": "system", "content": ENTITY_EXTRACTION_PROMPT},
            {"role": "user", "content": query},
        ]
        response = self.chat(messages, temperature=0.0, max_tokens=512)

        # 解析 LLM 输出的关键词列表
        entities = []
        for line in response.strip().split("\n"):
            line = line.strip().strip("-").strip("•").strip("*").strip()
            if line and len(line) > 1:
                entities.append(line)
        return entities


# ============================================================
#  Prompt 模板
# ============================================================

GRAPHRAG_SYSTEM_PROMPT = """You are a pharmaceutical supply chain expert assistant powered by a GraphRAG system. 
You have access to:
1. **Document evidence**: ICH guidelines (Q7 GMP, Q9 Risk Management, Q10 Quality System, Q12 Lifecycle, Q1A Stability) and academic papers on supply chain management.
2. **Knowledge Graph facts**: A structured graph of drugs, APIs (Active Pharmaceutical Ingredients), manufacturers, countries, therapeutic areas, shortage events, regulations, and their relationships.
3. **Risk propagation paths**: Supply chain dependency chains showing how disruptions propagate.

Answer the user's question based ONLY on the provided context. Be specific and cite sources:
- For document evidence, cite the document ID and section (e.g., "According to ICH Q7, Section 11...")
- For KG facts, cite the entities and relationships (e.g., "Amoxicillin depends on Amoxicillin Trihydrate supplied by Aurobindo...")
- For risk paths, describe the propagation chain

If the context doesn't contain enough information to fully answer, say so explicitly.
Respond in the same language as the user's question."""

ENTITY_EXTRACTION_PROMPT = """Extract pharmaceutical entity keywords from the user's question. 
Return one entity per line (drug names, API names, manufacturer names, country names, therapeutic areas, regulation names).
Only return entity names, no explanations.
If no specific entities are found, return general topic keywords.

Examples:
- Question: "What happens if Aurobindo stops producing Amoxicillin?"
  Aurobindo
  Amoxicillin

- Question: "What are the GMP requirements for API manufacturing?"
  GMP
  API manufacturing

- Question: "供应链中断对抗生素类药物的影响"
  抗生素
  Antibiotics"""
