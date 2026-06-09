import logging
import re
import requests
from config import settings

logger = logging.getLogger(__name__)

class RerankerService:
    @classmethod
    def rerank_candidates(cls, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        """
        Rerank retrieved candidates based on the configured RERANK_PROVIDER.
        Returns the top_k reranked candidates.
        """
        if not candidates:
            return []

        provider = str(getattr(settings, "RERANK_PROVIDER", "")).strip().lower()
        if not provider or provider == "none":
            # No reranking configured, return candidates truncated to top_k
            return candidates[:top_k]

        logger.info(f"Applying reranking for query='{query}' using provider='{provider}' on {len(candidates)} candidates")

        try:
            if provider == "llm":
                return cls._rerank_via_llm(query, candidates, top_k)
            elif provider == "local_lexical" or provider == "lexical":
                return cls._rerank_via_lexical(query, candidates, top_k)
            else:
                logger.warning(f"Unknown rerank provider '{provider}', falling back to default order")
                return candidates[:top_k]
        except Exception as e:
            logger.error(f"Reranking execution failed: {e}. Falling back to default order.", exc_info=True)
            return candidates[:top_k]

    @classmethod
    def _rerank_via_llm(cls, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        """
        Use the LLM2 model to evaluate and rank the candidates.
        """
        # Limit candidates to a reasonable size (e.g. top 10) to avoid huge prompts and high latency
        eval_candidates = candidates[:10]
        if len(eval_candidates) <= 1:
            return candidates[:top_k]

        # Format candidates for the prompt
        doc_str_list = []
        for idx, doc in enumerate(eval_candidates):
            title = doc.get("title") or "无标题"
            content = doc.get("content") or ""
            snippet = content[:300].replace("\n", " ")
            doc_str_list.append(f"[{idx}] 标题: {title} | 内容: {snippet}")

        docs_formatted = "\n".join(doc_str_list)

        prompt = f"""你是一个精确的检索文档精排重排器。请根据给定的用户查询，从候选文档列表中评估它们的相关性。
请按照相关度从高到低排序，只返回候选文档的索引序号列表，以逗号分隔（例如，如果第 2 个和第 0 个文档最相关，则输出：2, 0, 1）。
绝对不要解释任何内容，不要输出其他字符，不要输出 markdown 块。

用户查询: "{query}"

候选文档列表:
{docs_formatted}

输出格式样例：2, 0, 1
请立即输出排序索引列表："""

        # Call LLM2
        url = settings.LLM2_API_URL.rstrip('/') + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.LLM2_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": settings.LLM2_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 50
        }

        # Avoid proxy issues using a clean requests session
        session = requests.Session()
        session.trust_env = False
        res = session.post(url, json=payload, headers=headers, timeout=8)

        if res.status_code == 200:
            content = res.json()["choices"][0]["message"]["content"].strip()
            logger.info(f"LLM reranking response: '{content}'")
            # Parse indices (e.g., "2, 0, 1")
            indices = []
            for item in re.split(r"[,\s]+", content):
                item_clean = re.sub(r"\D", "", item)
                if item_clean.isdigit():
                    idx = int(item_clean)
                    if 0 <= idx < len(eval_candidates) and idx not in indices:
                        indices.append(idx)

            # Reorder eval_candidates based on returned indices
            reranked = [eval_candidates[idx] for idx in indices]
            # Append any candidates that were not returned by LLM to the end
            for idx, doc in enumerate(eval_candidates):
                if idx not in indices:
                    reranked.append(doc)

            # Add remaining original candidates that weren't sent to LLM evaluation
            reranked.extend(candidates[10:])
            return reranked[:top_k]
        else:
            logger.warning(f"LLM reranking API returned status code {res.status_code}, falling back to default order")
            return candidates[:top_k]

    @classmethod
    def _rerank_via_lexical(cls, query: str, candidates: list[dict], top_k: int) -> list[dict]:
        """
        Lightweight lexical re-ranker that calculates word-overlap, Jaccard distance,
        and updates the semantic cosine score.
        """
        # Tokenize query
        query_words = set(w for w in re.split(r"\s+", query.lower()) if len(w) >= 2)
        if not query_words:
            return candidates[:top_k]

        reranked_list = []
        for doc in candidates:
            content = str(doc.get("content") or "").lower()
            title = str(doc.get("title") or "").lower()
            haystack = title + " " + content

            # Term overlap count
            overlap_count = sum(1 for w in query_words if w in haystack)

            # Jaccard-like score
            doc_words = set(w for w in re.split(r"\W+", haystack) if len(w) >= 2)
            union = query_words.union(doc_words)
            jaccard = overlap_count / len(union) if union else 0.0

            # Lexical score
            lexical_score = (overlap_count / len(query_words)) * 0.7 + jaccard * 0.3

            # Combine with existing semantic/fused score
            current_score = float(doc.get("score") or 0.0)

            # Weighted formula: 60% original score + 40% lexical interactive score
            fused_score = current_score * 0.6 + lexical_score * 0.4

            # Update score copy to preserve metadata
            doc_copy = dict(doc)
            doc_copy["original_score"] = current_score
            doc_copy["lexical_score"] = round(lexical_score, 6)
            doc_copy["score"] = round(fused_score, 6)

            reranked_list.append(doc_copy)

        # Re-sort based on updated score
        reranked_list.sort(key=lambda x: x["score"], reverse=True)
        return reranked_list[:top_k]

    @staticmethod
    def reciprocal_rank_fusion(semantic_ranks: list[dict], keyword_ranks: list[dict], k: int = 60) -> list[dict]:
        """
        Standard Reciprocal Rank Fusion (RRF) algorithm.
        Merges two ranked candidate lists based on the ranks of their chunk_id/id.
        """
        rrf_scores = {}
        candidate_map = {}

        # 1. Process semantic ranks
        for rank_idx, item in enumerate(semantic_ranks):
            chunk_id = str(item.get("chunk_id") or item.get("id"))
            if not chunk_id:
                continue
            rank = rank_idx + 1  # 1-indexed
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + (1.0 / (k + rank))
            candidate_map[chunk_id] = item

        # 2. Process keyword ranks
        for rank_idx, item in enumerate(keyword_ranks):
            chunk_id = str(item.get("chunk_id") or item.get("id"))
            if not chunk_id:
                continue
            rank = rank_idx + 1  # 1-indexed
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + (1.0 / (k + rank))
            if chunk_id not in candidate_map:
                candidate_map[chunk_id] = item

        # 3. Sort candidates by RRF score descending
        sorted_chunk_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

        merged_candidates = []
        for cid in sorted_chunk_ids:
            item = candidate_map[cid]
            item_copy = dict(item)
            item_copy["rrf_score"] = round(rrf_scores[cid], 6)
            # Normalize RRF score to [0.0, 1.0] range for compatibility
            # Since max possible score with 2 lists at rank 1 is 2 / (k + 1)
            max_possible = 2.0 / (k + 1)
            item_copy["score"] = round(rrf_scores[cid] / max_possible, 6)
            merged_candidates.append(item_copy)

        logger.info(f"RRF merge complete: {len(semantic_ranks)} semantic, {len(keyword_ranks)} keyword -> {len(merged_candidates)} unique merged")
        return merged_candidates
