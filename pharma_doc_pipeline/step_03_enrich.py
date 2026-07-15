"""
Step 3: 内容富化 + HyDE 假设性问题生成 (C1/C2 策略版)
====================================================
  - C1 策略 (char_count > 500): 仅用 content 生成供应链聚焦 HyDE 问题
  - C2 策略 (char_count ≤ 500): 补充 5 项上下文后生成 HyDE 问题
  - 动态摘要 (超长 chunk 自动生成)
  - 表格自然语言摘要

支持 Ollama(本地) 和 DeepSeek API 两种 LLM 后端。
"""

import json
import time
import re
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import asdict

from .config import (CHUNKS_DIR, CACHE_DIR, PipelineSettings,
                     LLMConfig, ChunkingConfig, DOCUMENT_SOURCES)
from .step_02_chunk import ChunkNode


# ═══════════════════════════════════════════════════════════════
#  C1/C2 策略阈值
# ═══════════════════════════════════════════════════════════════
# 基于 2,741 chunks 的字符数分布分析:
#   中位数 620, 均值 786, P25=251
#   阈值 500: C1(>500)=56.8%, C2(≤500)=43.2%
# 短 chunk (≤500 字符) 约占 43%, 需要补充上下文增强独立性
C1_C2_THRESHOLD = 500


# ═══════════════════════════════════════════════════════════════
#  LLM 客户端
# ═══════════════════════════════════════════════════════════════

class LLMClient:
    """统一的 LLM 调用接口"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._session = None

    @property
    def session(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.trust_env = False
        return self._session

    def complete(self, prompt: str, system: str = "",
                 temperature: float = None) -> str:
        """调用 LLM, 返回纯文本回复"""
        temp = temperature if temperature is not None else self.config.temperature

        if self.config.backend == "ollama":
            return self._call_ollama(prompt, system, temp)
        else:
            return self._call_api(prompt, system, temp)

    def _call_ollama(self, prompt: str, system: str, temp: float) -> str:
        """Ollama 本地调用"""
        url = f"{self.config.ollama_host}/api/chat"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.config.ollama_model,
            "messages": messages,
            "options": {"temperature": temp},
            "stream": False,
        }

        try:
            r = self.session.post(url, json=payload,
                                  timeout=self.config.timeout)
            r.raise_for_status()
            return r.json()["message"]["content"]
        except Exception as e:
            print(f"    ⚠ Ollama 错误: {e}")
            return ""

    def _call_api(self, prompt: str, system: str, temp: float) -> str:
        """OpenAI 兼容 API 调用 (DeepSeek / OpenAI)，带重试"""
        import time as _time
        url = f"{self.config.api_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.config.api_model,
            "messages": messages,
            "temperature": temp,
            "max_tokens": self.config.max_tokens,
        }
        if self.config.api_extra_body:
            payload.update(self.config.api_extra_body)

        max_retries = 3
        for attempt in range(max_retries):
            try:
                r = self.session.post(url, json=payload, headers=headers,
                                      timeout=self.config.timeout)
                r.raise_for_status()
                data = r.json()
                return data["choices"][0]["message"]["content"]
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print(f"\n    ⚠ API 重试 ({attempt+1}/{max_retries}): {e}", end="", flush=True)
                    _time.sleep(wait)
                else:
                    print(f"\n    ⚠ API 错误 (已重试{max_retries}次): {e}")
                    return ""


# ═══════════════════════════════════════════════════════════════
#  Prompts — 供应链聚焦版
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are a pharmaceutical supply chain expert assistant.
You help analyze, clean, and summarize regulatory documents from FDA, ICH, WHO,
and other authorities related to drug manufacturing, quality, and supply chain management."""

CLEAN_PROMPT = """Clean and fix the following text extracted from a pharmaceutical document.
Fix any OCR errors, remove page headers/footers, normalize formatting.
Keep the original meaning. Only return the cleaned text, nothing else.

Text:
{text}"""

SUMMARY_PROMPT = """Summarize the following section from a pharmaceutical regulatory document.
Focus on: key requirements, risks, regulatory obligations, supply chain implications.
Keep the summary concise (3-5 sentences). Write in English.
Use only information explicitly supported by the excerpt and its context.
Do not introduce document names, standards, obligations, or supply chain implications that are absent.
If the excerpt is unrelated to pharmaceutical regulation, manufacturing quality, or supply chain risk,
return ONLY: [IRRELEVANT_SOURCE]

Section: {heading}
Context: {parents_context}

Content:
{content}"""

TABLE_SUMMARY_PROMPT = """Summarize the following Markdown table from a pharmaceutical regulatory document in 2-3 sentences of natural language.
Focus on: what data this table presents, key conditions/parameters, and how it relates to regulatory requirements.
Write in English. Only return the summary, nothing else.
Use only information explicitly supported by the table and heading.
Do not introduce document names, standards, or obligations that are absent.
If the table is unrelated to pharmaceutical regulation, manufacturing quality, or supply chain risk,
return ONLY: [IRRELEVANT_SOURCE]

Context (section heading): {heading}

Table:
{table}"""

# ── HyDE System Prompt (供应链风险分析师角色, C1/C2 共用) ──

HYDE_SYSTEM_PROMPT = """You are a pharmaceutical supply chain risk analyst with expertise in \
ICH/FDA/WHO regulatory frameworks. Your task is to anticipate questions that a supply chain \
risk manager, regulatory affairs specialist, or quality assurance manager would ask based on \
the given regulatory document excerpt."""

# ── C1 Prompt (chunk > 500 字符，内容丰富，仅 content) ──

HYDE_C1_PROMPT = """Below is an excerpt from a pharmaceutical regulatory document.

Document: {doc_meta}

Generate {n} source-grounded retrieval questions that a pharmaceutical supply chain \
risk manager, regulatory affairs specialist, or quality assurance manager would ask.
The excerpt must contain the answer.

Focus each question on one of these angles:
1. A compliance requirement, control, validation activity, quality risk, or data integrity obligation explicitly stated in the excerpt.
2. Affected products, APIs, manufacturers, suppliers, or supply chain nodes only when they are named or directly implied by the excerpt.
3. Risk-control or mitigation actions only when the excerpt explicitly describes those controls.
4. Regulatory or operational consequences only when the excerpt directly supports that consequence.

Rules:
- Write questions in English
- Each question must be self-contained (no pronouns referring to "this document")
- Keep each question concise; one sentence, no more than 320 characters
- Include a specific regulatory topic only when it is explicitly supported by the excerpt
- Do not invent or attribute ICH, FDA, WHO, or other standards unless the excerpt names them
- Do not introduce speculative terms such as import alert, recall, production halt, dual-sourcing, contingency plan, CMO, or single-source unless the excerpt directly supports them
- Do not ask what strategy should be established unless the excerpt states or clearly requires that strategy or control
- If the excerpt does not support a pharmaceutical regulatory or supply chain question, return ONLY: [IRRELEVANT_SOURCE]
- Return ONLY the questions, one per line, numbered

Content:
{content}"""

# ── C2 Prompt (chunk ≤ 500 字符，需上下文补充) ──

HYDE_C2_PROMPT = """Below is a short excerpt from a pharmaceutical regulatory document, along with \
contextual information to help you understand its scope.

Document: {doc_meta}
Document scope: {scope}
Parent section: {parent_section}
Surrounding context: {prev_next_50}
Related table info: {table_summary}

Generate {n} source-grounded retrieval questions that a pharmaceutical supply chain \
risk manager, regulatory affairs specialist, or quality assurance manager would ask.
The excerpt below, together with the supplied context, must contain the answer.

Focus each question on one of these angles:
1. A compliance requirement, control, validation activity, quality risk, or data integrity obligation explicitly stated in the excerpt or context.
2. Affected products, APIs, manufacturers, suppliers, or supply chain nodes only when they are named or directly implied by the excerpt or context.
3. Risk-control or mitigation actions only when the excerpt or context explicitly describes those controls.
4. Regulatory or operational consequences only when the excerpt or context directly supports that consequence.

Rules:
- Write questions in English
- Each question must be self-contained (no pronouns referring to "this document")
- Keep each question concise; one sentence, no more than 320 characters
- Include a specific regulatory topic only when it is explicitly supported by the excerpt or context
- Do not invent or attribute ICH, FDA, WHO, or other standards unless the excerpt or context names them
- Do not introduce speculative terms such as import alert, recall, production halt, dual-sourcing, contingency plan, CMO, or single-source unless the excerpt or context directly supports them
- Do not ask what strategy should be established unless the excerpt or context states or clearly requires that strategy or control
- If the excerpt does not support a pharmaceutical regulatory or supply chain question, return ONLY: [IRRELEVANT_SOURCE]
- Return ONLY the questions, one per line, numbered

Content:
{content}"""


# ═══════════════════════════════════════════════════════════════
#  内容富化器
# ═══════════════════════════════════════════════════════════════

SUMMARY_PROMPT_VERSION = "v2_source_grounded"
HYDE_PROMPT_VERSION = "v4_source_grounded_guarded"
TABLE_SUMMARY_PROMPT_VERSION = "v3_sha256_source_grounded"
IRRELEVANT_SOURCE_MARKER = "[IRRELEVANT_SOURCE]"
HYDE_MIN_QUESTION_CHARS = 25
HYDE_MAX_QUESTION_CHARS = 340
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
STANDARD_REFERENCE_RE = re.compile(
    r"\bICH\s+(?:Guideline\s+)?[QESM]\d+[A-Z0-9()/-]*",
    re.IGNORECASE,
)
NAMED_AUTHORITY_RE = re.compile(r"\b(?:FDA|WHO|EMA|ICH)\b", re.IGNORECASE)


class ContentEnricher:
    """内容富化: 清洗 + 摘要 + C1/C2 HyDE"""

    def __init__(self, settings: PipelineSettings = None):
        self.settings = settings or PipelineSettings()
        self.llm = LLMClient(self.settings.llm)
        self.config = self.settings.chunking

        # 缓存 (避免重复 LLM 调用)
        self.cache_path = CACHE_DIR / "enrichment_cache.json"
        self.cache = self._load_cache()
        self._call_count = 0

        # 构建 doc_id → DOCUMENT_SOURCES 映射 (用于 C2 上下文)
        self._doc_source_map = {d["id"]: d for d in DOCUMENT_SOURCES}

        # C1/C2 统计
        self._c1_count = 0
        self._c2_count = 0
        self._quality_counters = self._new_quality_counters()
        self._last_hyde_meta: Dict[str, Any] = {}

    @staticmethod
    def _new_quality_counters() -> Dict[str, int]:
        return {
            "chunks_seen": 0,
            "summary_eligible_chunks": 0,
            "summary_generated_chunks": 0,
            "summary_irrelevant_chunks": 0,
            "hyde_eligible_chunks": 0,
            "hyde_too_short_chunks": 0,
            "hyde_generated_chunks": 0,
            "hyde_questions_generated": 0,
            "hyde_irrelevant_chunks": 0,
            "hyde_empty_outputs": 0,
            "hyde_c1_chunks": 0,
            "hyde_c2_chunks": 0,
            "hyde_malformed_questions_filtered": 0,
            "hyde_cjk_questions_filtered": 0,
            "hyde_too_long_questions_filtered": 0,
            "hyde_unsupported_reference_questions_filtered": 0,
            "table_summary_eligible": 0,
            "table_summary_generated": 0,
            "table_summary_irrelevant": 0,
            "table_summary_existing": 0,
        }

    def _ensure_quality_counters(self) -> None:
        if not hasattr(self, "_quality_counters"):
            self._quality_counters = self._new_quality_counters()

    def _bump(self, key: str, amount: int = 1) -> None:
        self._ensure_quality_counters()
        self._quality_counters[key] = self._quality_counters.get(key, 0) + amount

    def _summary_eligible(self, chunk: ChunkNode) -> bool:
        return (
            chunk.line_count >= self.config.summary_trigger_lines
            or chunk.char_count >= self.config.summary_trigger_chars
        )

    def _hyde_eligible(self, chunk: ChunkNode) -> bool:
        return bool(self.config.enable_hyde and chunk.char_count >= 100)

    @staticmethod
    def _hyde_strategy_for(chunk: ChunkNode) -> str:
        return "C1" if chunk.char_count > C1_C2_THRESHOLD else "C2"

    def _llm_model_name(self) -> str:
        if self.settings.llm.backend == "ollama":
            return self.settings.llm.ollama_model
        return self.settings.llm.api_model

    def get_runtime_quality_report(self) -> Dict[str, Any]:
        self._ensure_quality_counters()
        return {
            "prompt_versions": {
                "summary": SUMMARY_PROMPT_VERSION,
                "hyde": HYDE_PROMPT_VERSION,
                "table_summary": TABLE_SUMMARY_PROMPT_VERSION,
            },
            "llm": {
                "backend": self.settings.llm.backend,
                "model": self._llm_model_name(),
            },
            "counters": dict(self._quality_counters),
            "new_llm_calls": self._call_count,
        }

    def _load_cache(self) -> Dict:
        if self.cache_path.exists():
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        with open(self.cache_path, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)

    def _cached_call(self, cache_key: str, prompt: str,
                     system: str = SYSTEM_PROMPT) -> str:
        """带缓存的 LLM 调用"""
        if cache_key in self.cache:
            return self.cache[cache_key]

        result = self.llm.complete(prompt, system=system)
        if result:
            self.cache[cache_key] = result
            self._call_count += 1
            # 每10次调用保存一次缓存
            if self._call_count % 10 == 0:
                self._save_cache()
        return result

    # ──────── 清洗 ────────

    def clean_content(self, chunk: ChunkNode) -> str:
        """LLM 清洗 chunk 内容"""
        if chunk.char_count < 50:
            return chunk.content

        cache_key = f"clean_{chunk.chunk_id}"
        prompt = CLEAN_PROMPT.format(text=chunk.content[:3000])
        result = self._cached_call(cache_key, prompt)
        return result if result else chunk.content

    # ──────── 摘要 ────────

    def generate_summary(self, chunk: ChunkNode) -> Optional[str]:
        """为超长 chunk 生成摘要"""
        if not self._summary_eligible(chunk):
            return None

        self._bump("summary_eligible_chunks")
        cache_key = f"summary_{SUMMARY_PROMPT_VERSION}_{chunk.chunk_id}"
        prompt = SUMMARY_PROMPT.format(
            heading=chunk.heading,
            parents_context=chunk.parents_context,
            content=chunk.content[:4000]
        )
        result = self._cached_call(cache_key, prompt)
        if result and IRRELEVANT_SOURCE_MARKER in result:
            self._bump("summary_irrelevant_chunks")
            return None
        if result:
            self._bump("summary_generated_chunks")
        return result

    def _get_doc_meta(self, doc_id: str) -> str:
        doc_info = self._doc_source_map.get(doc_id)
        if not doc_info:
            return doc_id
        return f'{doc_info["title"]} ({doc_info["authority"]})'

    @staticmethod
    def _normalize_reference(text: str) -> str:
        return re.sub(r"[^a-z0-9]", "", text.lower())

    @staticmethod
    def _table_cache_key(table_markdown: str) -> str:
        digest = hashlib.sha256(table_markdown.encode("utf-8")).hexdigest()[:16]
        return f"table_summary_{TABLE_SUMMARY_PROMPT_VERSION}_{digest}"

    def _has_supported_named_references(self, question: str,
                                        chunk: ChunkNode) -> bool:
        supported_text = " ".join(
            (
                self._get_doc_meta(chunk.doc_id),
                chunk.heading,
                chunk.parents_context,
                chunk.content,
            )
        )
        normalized_supported = self._normalize_reference(supported_text)
        supported_authorities = {
            match.group(0).upper()
            for match in NAMED_AUTHORITY_RE.finditer(supported_text)
        }

        for match in NAMED_AUTHORITY_RE.finditer(question):
            if match.group(0).upper() not in supported_authorities:
                return False

        for match in STANDARD_REFERENCE_RE.finditer(question):
            if self._normalize_reference(match.group(0)) not in normalized_supported:
                return False

        return True

    @staticmethod
    def _strip_question_prefix(line: str) -> str:
        line = line.strip()
        line = re.sub(r'^(?:[-*]\s*)?\d+[.)]\s*', '', line)
        line = re.sub(r'^[-*]\s*', '', line)
        return line.strip()

    @staticmethod
    def _hyde_question_rejection_reason(question: str) -> Optional[str]:
        q = " ".join(question.split())
        if len(q) < HYDE_MIN_QUESTION_CHARS or not q.endswith("?"):
            return "malformed"
        if CJK_RE.search(q):
            return "cjk"
        if len(q) > HYDE_MAX_QUESTION_CHARS:
            return "too_long"
        return None

    # ──────── C2 上下文构建 ────────

    def _build_c2_context(self, chunk: ChunkNode,
                          all_chunks: List[ChunkNode]) -> dict:
        """
        为 ≤500 字符的短 chunk 构建 5 项上下文,
        消除代词歧义, 增强 chunk 的独立可理解性。
        """
        ctx = {}

        # 1. doc_meta: 文档标题 + 机构
        ctx["doc_meta"] = self._get_doc_meta(chunk.doc_id)

        # 2. scope: 同文档中 heading 含 "Scope"/"范围" 的 chunk, 取前 300 字
        scope_chunk = next(
            (c for c in all_chunks
             if c.doc_id == chunk.doc_id and
             re.search(r'\bScope\b|范围', c.heading, re.IGNORECASE)),
            None
        )
        ctx["scope"] = scope_chunk.content[:300] if scope_chunk else "(not available)"

        # 3. parent_section: 直接用 parents_context 面包屑
        ctx["parent_section"] = chunk.parents_context or "(top-level)"

        # 4. prev_next_50: 前后 chunk 各取 50 字符
        prev_text = ""
        next_text = ""
        if chunk.prev_chunk_id:
            prev_c = next(
                (c for c in all_chunks if c.chunk_id == chunk.prev_chunk_id),
                None
            )
            if prev_c:
                prev_text = prev_c.content[-50:]
        if chunk.next_chunk_id:
            next_c = next(
                (c for c in all_chunks if c.chunk_id == chunk.next_chunk_id),
                None
            )
            if next_c:
                next_text = next_c.content[:50]
        parts = []
        if prev_text:
            parts.append(f"[Before] ...{prev_text}")
        if next_text:
            parts.append(f"[After] {next_text}...")
        ctx["prev_next_50"] = " ".join(parts) if parts else "(not available)"

        # 5. table_summary: 同 section 下表格 chunk 的摘要, 取前 100 字
        parent_heading = ""
        if chunk.parents_context:
            segments = chunk.parents_context.split(" > ")
            parent_heading = segments[-1] if segments else ""

        table_summaries = []
        if parent_heading:
            table_chunks = [
                c for c in all_chunks
                if (c.doc_id == chunk.doc_id and
                    c.has_table and
                    parent_heading in (c.parents_context or ""))
            ]
            for tc in table_chunks[:2]:  # 最多取 2 个
                for tr in tc.table_refs[:1]:  # 每个 chunk 取第一个表
                    ts = self.generate_table_summary(tr, heading=tc.heading)
                    if ts:
                        table_summaries.append(ts[:100])

        ctx["table_summary"] = " | ".join(table_summaries) if table_summaries else "(no tables in this section)"

        return ctx

    # ──────── HyDE (C1/C2 策略) ────────

    def generate_hyde_questions(self, chunk: ChunkNode,
                                all_chunks: List[ChunkNode] = None) -> List[str]:
        """
        C1/C2 策略生成供应链聚焦的 HyDE 假设性问题。
        
        C1 (char_count > 500): 仅用 content, 内容足够丰富
        C2 (char_count ≤ 500): 补充 5 项上下文 (doc_meta, scope,
            parent_section, prev_next_50, table_summary)
        """
        self._last_hyde_meta = {
            "eligible": False,
            "strategy": None,
            "questions_requested": 0,
            "questions_generated": 0,
            "irrelevant_source": False,
            "empty_output": False,
            "malformed_questions_filtered": 0,
            "cjk_questions_filtered": 0,
            "too_long_questions_filtered": 0,
            "unsupported_named_reference_questions_filtered": 0,
        }

        if not self.config.enable_hyde:
            return []
        if chunk.char_count < 100:
            self._bump("hyde_too_short_chunks")
            return []

        n = self.config.hyde_questions_per_chunk
        strategy = self._hyde_strategy_for(chunk)
        self._bump("hyde_eligible_chunks")
        self._bump(f"hyde_{strategy.lower()}_chunks")
        self._last_hyde_meta.update({
            "eligible": True,
            "strategy": strategy,
            "questions_requested": n,
        })

        if chunk.char_count > C1_C2_THRESHOLD:
            # ── C1 策略: 仅 content ──
            cache_key = f"hyde_c1_{HYDE_PROMPT_VERSION}_{chunk.chunk_id}_{n}"
            prompt = HYDE_C1_PROMPT.format(
                n=n,
                doc_meta=self._get_doc_meta(chunk.doc_id),
                content=chunk.content[:3000]
            )
            self._c1_count += 1
        else:
            # ── C2 策略: 补充上下文 ──
            cache_key = f"hyde_c2_{HYDE_PROMPT_VERSION}_{chunk.chunk_id}_{n}"
            ctx = self._build_c2_context(chunk, all_chunks or [])
            prompt = HYDE_C2_PROMPT.format(
                n=n,
                content=chunk.content[:3000],
                **ctx
            )
            self._c2_count += 1

        result = self._cached_call(cache_key, prompt, system=HYDE_SYSTEM_PROMPT)

        if not result:
            self._bump("hyde_empty_outputs")
            self._last_hyde_meta["empty_output"] = True
            return []
        if IRRELEVANT_SOURCE_MARKER in result:
            self._bump("hyde_irrelevant_chunks")
            self._last_hyde_meta["irrelevant_source"] = True
            return []

        # 解析 numbered questions
        questions = []
        malformed_count = 0
        cjk_count = 0
        too_long_count = 0
        unsupported_reference_count = 0
        for line in result.strip().split('\n'):
            line = self._strip_question_prefix(line)
            if not line:
                continue
            rejection_reason = self._hyde_question_rejection_reason(line)
            if rejection_reason == "malformed":
                malformed_count += 1
                continue
            if rejection_reason == "cjk":
                cjk_count += 1
                continue
            if rejection_reason == "too_long":
                too_long_count += 1
                continue
            if self._has_supported_named_references(line, chunk):
                questions.append(" ".join(line.split()))
            else:
                unsupported_reference_count += 1

        questions = questions[:n]
        if questions:
            self._bump("hyde_generated_chunks")
            self._bump("hyde_questions_generated", len(questions))
        if malformed_count:
            self._bump("hyde_malformed_questions_filtered", malformed_count)
        if cjk_count:
            self._bump("hyde_cjk_questions_filtered", cjk_count)
        if too_long_count:
            self._bump("hyde_too_long_questions_filtered", too_long_count)
        if unsupported_reference_count:
            self._bump(
                "hyde_unsupported_reference_questions_filtered",
                unsupported_reference_count,
            )
        self._last_hyde_meta.update({
            "questions_generated": len(questions),
            "malformed_questions_filtered": malformed_count,
            "cjk_questions_filtered": cjk_count,
            "too_long_questions_filtered": too_long_count,
            "unsupported_named_reference_questions_filtered": (
                unsupported_reference_count
            ),
        })
        return questions

    # ──────── 表格摘要 ────────

    def generate_table_summary(self, table_markdown: str,
                                heading: str = "") -> str:
        """为 Markdown 表格生成自然语言摘要"""
        if not table_markdown or len(table_markdown) < 20:
            return ""

        self._bump("table_summary_eligible")
        cache_key = self._table_cache_key(table_markdown)
        prompt = TABLE_SUMMARY_PROMPT.format(
            heading=heading,
            table=table_markdown[:3000]
        )
        result = self._cached_call(cache_key, prompt)
        if result and IRRELEVANT_SOURCE_MARKER in result:
            self._bump("table_summary_irrelevant")
            return ""
        if result:
            self._bump("table_summary_generated")
        return result

    # ──────── 主流程 ────────

    def enrich_chunks(self, chunks: List[ChunkNode],
                      all_chunks: List[ChunkNode] = None,
                      doc_id: str = "") -> List[Dict]:
        """
        富化一组 chunks:
          1. 生成摘要 (可选)
          2. 生成 HyDE 假设性问题 (C1/C2 策略)

        返回 enriched records (dict list)
        """
        enriched = []
        # 如果没有传入全量 chunks, 用当前 chunks 作为上下文
        context_chunks = all_chunks if all_chunks else chunks

        for i, chunk in enumerate(chunks):
            self._bump("chunks_seen")
            record = asdict(chunk)
            summary_eligible = self._summary_eligible(chunk)
            hyde_eligible = self._hyde_eligible(chunk)
            hyde_strategy = self._hyde_strategy_for(chunk) if hyde_eligible else None

            # 摘要
            summary = self.generate_summary(chunk)
            if summary:
                record["summary"] = summary
                record["search_text"] = (
                    chunk.parents_context + "\n" +
                    chunk.heading + "\n" +
                    summary + "\n" +
                    chunk.content
                )

            # HyDE 问题 (C1/C2 策略)
            hyde_qs = self.generate_hyde_questions(chunk, context_chunks)
            hyde_meta = dict(getattr(self, "_last_hyde_meta", {}))
            if hyde_qs:
                record["hyde_questions"] = hyde_qs
                # 标记使用了哪种策略
                record["hyde_strategy"] = (
                    "C1" if chunk.char_count > C1_C2_THRESHOLD else "C2"
                )

            record["enrichment_meta"] = {
                "summary_prompt_version": SUMMARY_PROMPT_VERSION,
                "hyde_prompt_version": HYDE_PROMPT_VERSION,
                "table_summary_prompt_version": TABLE_SUMMARY_PROMPT_VERSION,
                "llm_backend": self.settings.llm.backend,
                "llm_model": self._llm_model_name(),
                "summary_eligible": summary_eligible,
                "summary_generated": bool(summary),
                "hyde_enabled": bool(self.config.enable_hyde),
                "hyde_eligible": hyde_eligible,
                "hyde_strategy": hyde_strategy,
                "hyde_questions_requested": hyde_meta.get(
                    "questions_requested", 0
                ),
                "hyde_questions_generated": len(hyde_qs),
                "source_grounding": {
                    "irrelevant_marker": bool(
                        hyde_meta.get("irrelevant_source", False)
                    ),
                    "named_reference_filter": True,
                    "malformed_questions_filtered": hyde_meta.get(
                        "malformed_questions_filtered", 0
                    ),
                    "cjk_questions_filtered": hyde_meta.get(
                        "cjk_questions_filtered", 0
                    ),
                    "too_long_questions_filtered": hyde_meta.get(
                        "too_long_questions_filtered", 0
                    ),
                    "unsupported_named_reference_questions_filtered": (
                        hyde_meta.get(
                            "unsupported_named_reference_questions_filtered",
                            0,
                        )
                    ),
                },
            }

            enriched.append(record)

            # 进度
            if (i + 1) % 10 == 0:
                print(f"    进度: {i+1}/{len(chunks)}", flush=True)

        return enriched

    def enrich_all(self, chunks_dir: Path = None) -> Dict[str, List[Dict]]:
        """批量富化所有 chunk 文件 + 表格文件"""
        chunks_dir = chunks_dir or CHUNKS_DIR
        chunk_files = sorted(chunks_dir.glob("*_chunks.json"))

        if not chunk_files:
            print("  ⚠ 无 chunk 文件可富化")
            return {}

        print(f"╔{'═' * 50}╗")
        print(f"║  内容富化 — 共 {len(chunk_files)} 个文档")
        print(f"║  LLM: {self.settings.llm.backend}")
        print(f"║  HyDE: {'启用' if self.config.enable_hyde else '禁用'}")
        print(f"║  策略: C1(>{C1_C2_THRESHOLD}字符) / C2(≤{C1_C2_THRESHOLD}字符)")
        print(f"║  表格摘要: 启用")
        print(f"╚{'═' * 50}╝\n")

        all_results = {}
        total_enriched = 0

        for cf in chunk_files:
            doc_id = cf.stem.replace("_chunks", "")

            # 跳过已富化的文档
            out_file = chunks_dir / f"{doc_id}_enriched.json"
            if out_file.exists():
                print(f"  ✓ {doc_id}: 已富化（跳过）", flush=True)
                with open(out_file, 'r', encoding='utf-8') as f:
                    enriched = json.load(f)
                all_results[doc_id] = enriched
                total_enriched += len(enriched)
                tables_file = chunks_dir / f"{doc_id}_tables.json"
                if tables_file.exists():
                    with open(cf, 'r', encoding='utf-8') as f:
                        raw_chunks = json.load(f)
                    chunks = []
                    for r in raw_chunks:
                        node_fields = {
                            k: v for k, v in r.items()
                            if k in ChunkNode.__dataclass_fields__
                        }
                        chunks.append(ChunkNode(**node_fields))
                    self._enrich_tables(tables_file, chunks)
                continue

            print(f"  📄 {doc_id}...", flush=True)

            with open(cf, 'r', encoding='utf-8') as f:
                raw_chunks = json.load(f)

            # 还原为 ChunkNode
            chunks = []
            for r in raw_chunks:
                # 过滤掉不属于 ChunkNode 的字段
                node_fields = {k: v for k, v in r.items()
                               if k in ChunkNode.__dataclass_fields__}
                chunks.append(ChunkNode(**node_fields))

            try:
                enriched = self.enrich_chunks(
                    chunks, all_chunks=chunks, doc_id=doc_id
                )
            except Exception as e:
                print(f"    ✗ {doc_id} 富化失败: {e}")
                self._save_cache()  # 保存已有缓存
                continue

            all_results[doc_id] = enriched
            total_enriched += len(enriched)

            # 立即保存该文档结果
            with open(out_file, 'w', encoding='utf-8') as f:
                json.dump(enriched, f, ensure_ascii=False, indent=2)

            hyde_count = sum(1 for e in enriched if e.get("hyde_questions"))
            summary_count = sum(1 for e in enriched if e.get("summary"))
            c1_in_doc = sum(1 for e in enriched if e.get("hyde_strategy") == "C1")
            c2_in_doc = sum(1 for e in enriched if e.get("hyde_strategy") == "C2")
            print(f"    → {len(enriched)} chunks, "
                  f"{summary_count} summaries, {hyde_count} HyDE sets "
                  f"(C1:{c1_in_doc}, C2:{c2_in_doc})")

            # ── 表格摘要生成 ──
            tables_file = chunks_dir / f"{doc_id}_tables.json"
            if tables_file.exists():
                self._enrich_tables(tables_file, chunks)

        # 最终保存缓存
        self._save_cache()

        print(f"\n✅ 富化完成: {total_enriched} chunks, "
              f"{self._call_count} LLM calls")
        print(f"   C1/C2 统计: C1={self._c1_count}, C2={self._c2_count}")
        return all_results

    def _enrich_tables(self, tables_file: Path, chunks: List[ChunkNode]):
        """为 tables.json 中的每张表格生成自然语言摘要"""
        with open(tables_file, 'r', encoding='utf-8') as f:
            tables = json.load(f)

        if not tables:
            return

        # 构建 chunk_id → heading 映射
        heading_map = {c.chunk_id: c.heading for c in chunks}

        updated = 0
        for t in tables:
            if t.get("table_summary"):
                self._bump("table_summary_existing")
                continue  # 已有摘要, 跳过

            heading = heading_map.get(t.get("chunk_id", ""), "")
            summary = self.generate_table_summary(
                t.get("table", ""), heading=heading
            )
            if summary:
                t["table_summary"] = summary
                updated += 1

        # 回写
        if updated > 0:
            with open(tables_file, 'w', encoding='utf-8') as f:
                json.dump(tables, f, ensure_ascii=False, indent=2)
            print(f"    📊 {tables_file.name}: {updated} 表格摘要已生成")


def run(**kwargs) -> Dict[str, List[Dict]]:
    """Step 3 入口"""
    settings = kwargs.get("settings", PipelineSettings())
    enricher = ContentEnricher(settings=settings)
    return enricher.enrich_all()
