import os
import sys
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Setup sys.path
backend_path = os.path.dirname(os.path.abspath(__file__))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_kb3")

# Load env variables from .env
dotenv_path = os.path.join(os.path.dirname(backend_path), ".env")
if os.path.exists(dotenv_path):
    with open(dotenv_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from database import SessionLocal, LlmServiceKnowledgeUnit
from embedding_service import EmbeddingService

def clean_punctuation(text):
    puncts = ["，", "。", "；", "？", "！", "、", "（", "）", "(", ")", ",", ".", "?", "!", ";", ":", "：", "\"", "'", "“", "”", "/", "+"]
    res = text
    for p in puncts:
        res = res.replace(p, " ")
    return res

def embed_unit(unit_id, text_to_embed):
    """Worker task to fetch embedding for a single text using mutations on failure."""
    vector = None
    max_retries = 4
    
    # Text mutations to bypass Ollama's attention layer NaN serialization bugs
    text_variants = [
        text_to_embed,
        clean_punctuation(text_to_embed),
        clean_punctuation(text_to_embed)[:50],
        clean_punctuation(text_to_embed)[:30]
    ]
    
    for attempt in range(max_retries):
        current_text = text_variants[min(attempt, len(text_variants) - 1)]
        try:
            vector = EmbeddingService.embed(current_text)
            if vector:
                return unit_id, vector
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"Error embedding unit ID={unit_id} (Attempt {attempt+1}/{max_retries}): {e}")
            else:
                # Sleep a tiny bit before retry (50ms) to allow minor breath room
                time.sleep(0.05)
                
    return unit_id, None

def main():
    logger.info("Starting concurrent KB3 embedding backfill process...")
    db = SessionLocal()
    try:
        # Query all units with missing embedding
        units = db.query(LlmServiceKnowledgeUnit).filter(
            LlmServiceKnowledgeUnit.embedding.is_(None)
        ).all()
        
        total = len(units)
        logger.info(f"Found {total} units with missing embeddings.")
        if total == 0:
            logger.info("Nothing to backfill. Exiting.")
            return

        # Prepare payload tuples (unit_id, text)
        units_data = [(u.unit_id, (u.search_text or u.title or "").strip()) for u in units]
        
        success_count = 0
        fail_count = 0
        batch_size = 50
        
        # Batch updates to save memory and commit incrementally
        for idx in range(0, total, batch_size):
            batch_data = units_data[idx : idx + batch_size]
            batch_units = units[idx : idx + batch_size]
            
            logger.info(f"Processing batch {idx // batch_size + 1}/{(total + batch_size - 1) // batch_size} (concurrently)...")
            
            results_by_id = {}
            
            # Execute embedding generation in parallel using 8 threads
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = {executor.submit(embed_unit, uid, txt): uid for uid, txt in batch_data if txt}
                
                for future in as_completed(futures):
                    uid = futures[future]
                    try:
                        _, vector = future.result()
                        if vector:
                            results_by_id[uid] = vector
                            success_count += 1
                        else:
                            fail_count += 1
                    except Exception as e:
                        logger.error(f"Thread execution error for unit ID={uid}: {e}")
                        fail_count += 1
            
            # Apply results and commit batch in the main thread
            for unit in batch_units:
                if unit.unit_id in results_by_id:
                    unit.embedding = results_by_id[unit.unit_id]
            
            try:
                db.commit()
                logger.info(f"Batch committed successfully. Cumulative Success={success_count}, Fail={fail_count}")
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to commit batch updates: {e}")
            
            # Sleep briefly between batches (100ms) to prevent server throttling
            time.sleep(0.1)
            
        logger.info(f"Concurrent backfill finished. Total: {total}, Success: {success_count}, Fail: {fail_count}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
