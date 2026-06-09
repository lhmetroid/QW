import unittest
import re
import uuid
from sqlalchemy.orm import Session
from database import SessionLocal, MessageLog, KnowledgeChunk
from agent_builder.models import BuilderSandboxSession
from config import settings
from reranker import RerankerService
from intent_engine import IntentEngine
from agent_builder.engine import extract_slots_from_message, run_sandbox_agentic_flow

class OptimizationsChecks(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_rrf_merging(self):
        """Test RRF reciprocal rank fusion merging"""
        semantic_list = [
            {"chunk_id": "doc_a", "content": "hello world from semantic"},
            {"chunk_id": "doc_b", "content": "foo bar from semantic"},
        ]
        keyword_list = [
            {"chunk_id": "doc_b", "content": "foo bar from keyword"},
            {"chunk_id": "doc_c", "content": "extra content from keyword"},
        ]

        fused = RerankerService.reciprocal_rank_fusion(semantic_list, keyword_list, k=60)
        self.assertTrue(len(fused) >= 3)
        # doc_b should be first because it appears in both lists
        self.assertEqual(fused[0]["chunk_id"], "doc_b")

    def test_lexical_rerank(self):
        """Test Lexical re-ranker Jaccard and word overlap calculation"""
        query = "iPhone XR price"
        candidates = [
            {"chunk_id": "1", "title": "About standard battery life", "content": "Our phones have great battery life.", "score": 0.8},
            {"chunk_id": "2", "title": "iPhone XR Retail Info", "content": "The iPhone XR is priced at 300 million Rupiah.", "score": 0.75},
        ]

        original_provider = getattr(settings, "RERANK_PROVIDER", "")
        try:
            settings.RERANK_PROVIDER = "local_lexical"
            settings.RERANK_ENABLED = True
            reranked = RerankerService.rerank_candidates(query, candidates, top_k=2)
            self.assertEqual(len(reranked), 2)
            # Candidate 2 should be ranked first now because it matches query keywords "iPhone XR"
            self.assertEqual(reranked[0]["chunk_id"], "2")
        finally:
            settings.RERANK_PROVIDER = original_provider

    def test_query_rewriting_empty_history(self):
        """Test query rewriting returns original query when history is empty or short"""
        query = "How to pay?"
        rewritten = IntentEngine.rewrite_query_v2(self.db, query, str(uuid.uuid4()))
        self.assertEqual(rewritten, query)

    def test_agentic_planner_and_reflection(self):
        """Test the Agentic Planner slot output and reflection self-correction checks"""
        # 1. Test offline regex planned_intent
        res_slots = extract_slots_from_message("我想咨询一下分期怎么算")
        self.assertEqual(res_slots.get("ask_installment"), True)
        self.assertEqual(res_slots.get("planned_intent"), "installment_rules")

        # 2. Test reflection interception for proactive installment leak
        # Create a mock session with a valid UUID
        session = BuilderSandboxSession(
            session_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            status="active",
            variables={
                "budget": "未收集",
                "phone_usage": "未收集",
                "battery_health": "未收集",
                "age": "未收集",
                "job": "未收集",
                "ktp": "未收集",
                "current_node": "需求探询与推荐",
                "installment_triggered": False,
                "details_verified": "未核实"
            }
        )

        # We simulate the LLM returning a message containing "分期" (which is prohibited when installment_triggered is False)
        # To do this, we override IntentEngine._post_json for the duration of this test
        original_post = IntentEngine._post_json
        try:
            class MockResponse:
                status_code = 200
                def json(self):
                    return {
                        "choices": [{
                            "message": {
                                "content": "我们可以为您办理分期付款哦，首付只需要10%起。"
                            }
                        }]
                    }
            IntentEngine._post_json = lambda *args, **kwargs: MockResponse()

            # Run the agentic flow
            reply_text, trace = run_sandbox_agentic_flow(self.db, session, "我想看 iPhone XR")

            # The reflection gate should have intercepted and corrected this proactively
            self.assertIn("reflection_triggered", trace)
            self.assertEqual(trace["reflection_triggered"], True)
            self.assertNotIn("分期付款", reply_text)
            self.assertIn("全款", reply_text)
        finally:
            IntentEngine._post_json = original_post

    def test_reflection_price_correction(self):
        """Test pricing mismatch self-correction in Reflection layer"""
        session = BuilderSandboxSession(
            session_id=str(uuid.uuid4()),
            agent_id=str(uuid.uuid4()),
            status="active",
            variables={
                "budget": "300万",
                "phone_usage": "拍照",
                "battery_health": "未收集",
                "age": "25",
                "job": "固定工作",
                "ktp": "持有",
                "current_node": "需求探询与推荐",
                "installment_triggered": True,
                "details_verified": "已核实"
            }
        )

        # We simulate the LLM returning a wrong price for iPhone XR (200万 instead of 300万)
        original_post = IntentEngine._post_json
        try:
            class MockResponse:
                status_code = 200
                def json(self):
                    return {
                        "choices": [{
                            "message": {
                                "content": "iPhone XR 这款手机只要 200万 就可以买到了。"
                            }
                        }]
                    }
            IntentEngine._post_json = lambda *args, **kwargs: MockResponse()

            reply_text, trace = run_sandbox_agentic_flow(self.db, session, "iPhone XR 多少钱？")

            # Reflection should correct the price to 300万
            self.assertIn("reflection_triggered", trace)
            self.assertEqual(trace["reflection_triggered"], True)
            self.assertTrue("300" in reply_text)
        finally:
            IntentEngine._post_json = original_post

    def test_chunk_overlap(self):
        """Test sliding window paragraph overlap chunking"""
        content = "Paragraph 1: This is the first paragraph.\n\nParagraph 2: This is the second one.\n\nParagraph 3: This is the third one."

        # Test paragraph overlap with custom bounds
        paragraphs = [p.strip() for p in re.split(r'\n+', content) if p.strip()]
        overlap_size = 50
        chunk_max_size = 80  # small max size to force split

        chunks = []
        current_chunk_paragraphs = []
        current_len = 0

        for p in paragraphs:
            if current_len + (1 if current_len > 0 else 0) + len(p) > chunk_max_size:
                if current_chunk_paragraphs:
                    chunk_text = "\n".join(current_chunk_paragraphs)
                    chunks.append(chunk_text)

                    overlap_paragraphs = []
                    overlap_len = 0
                    for op in reversed(current_chunk_paragraphs):
                        if overlap_len + (1 if overlap_len > 0 else 0) + len(op) <= overlap_size:
                            overlap_paragraphs.insert(0, op)
                            overlap_len += len(op) + 1
                        else:
                            break
                    current_chunk_paragraphs = overlap_paragraphs + [p]
                    current_len = sum(len(x) for x in current_chunk_paragraphs) + len(current_chunk_paragraphs) - 1
                else:
                    chunks.append(p)
                    current_chunk_paragraphs = []
                    current_len = 0
            else:
                current_chunk_paragraphs.append(p)
                current_len += (1 if current_len > 0 else 0) + len(p)

        if current_chunk_paragraphs:
            chunks.append("\n".join(current_chunk_paragraphs))

        self.assertTrue(len(chunks) >= 2)
        # Chunk 0 should have Paragraph 2, and Chunk 1 should have Paragraph 2 as overlap
        self.assertIn("Paragraph 2", chunks[0])
        self.assertIn("Paragraph 2", chunks[1])
        self.assertIn("Paragraph 3", chunks[1])

if __name__ == "__main__":
    unittest.main()
