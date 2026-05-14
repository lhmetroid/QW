import csv
import re
import os

def refine_text(text, is_question=True):
    if not text:
        return ""
    
    # 1. Remove "我通过了你的联系人验证请求..."
    text = text.replace("我通过了你的联系人验证请求，现在我们可以开始聊天了", "")
    
    # 2. Standardize quote format if needed (already handled by extraction)
    
    # 3. Remove common name/salutation prefixes (only if followed by punctuation)
    # This pattern targets: "Tony, ", "张经理: ", "李大哥，"
    # But avoids stripping common words like "但是，", "所以，"
    salutations = ["经理", "老师", "总", "哥", "姐", "主任", "主管", "部长"]
    salutation_regex = f"^[^\s，,]{{1,4}}({'|'.join(salutations)})[，,：:\s]+"
    text = re.sub(salutation_regex, "", text)
    
    # Also handle English names like "Tony, "
    text = re.sub(r"^[A-Z][a-z]{1,10}[，,：:\s]+", "", text)

    # 4. Remove leading emojis/symbols from Questions (better for retrieval)
    if is_question:
        # Matches patterns like [太阳], [愉快], [玫瑰], ??, !! at the start
        text = re.sub(r"^(\[[^\]]+\]|[\s\?？!！\.。，,、\^]+)+", "", text)

    # 5. Clean up leading/trailing whitespace
    text = text.strip()
    
    return text

def is_valuable(q, a):
    # Filter out empty or near-empty pairs
    if not q or not a:
        return False
    
    # Filter out questions that are just punctuation or very short noise
    if len(q) < 2 or re.match(r"^[\s\?？!！\.。，,、\^\[\]\(\)]+$", q):
        return False
    
    # Filter out common "No-op" answers if they are the ONLY content
    low_value_answers = ["好的", "没问题", "收到", "OK", "ok", "知道", "恩", "嗯", "好的呢"]
    if a in low_value_answers:
        return False

    # Filter out pairs that are just media placeholders with no text
    media_pattern = r"^\[图片/文件/语音\]$"
    if re.match(media_pattern, q) and re.match(media_pattern, a):
        return False
        
    return True

def finalize_kb(input_file, output_file):
    print(f"Finalizing Knowledge Base: {input_file}")
    
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found.")
        return

    with open(input_file, 'r', encoding='utf-8-sig') as f_in, \
         open(output_file, 'w', encoding='utf-8-sig', newline='') as f_out:
        
        reader = csv.DictReader(f_in)
        writer = csv.writer(f_out)
        writer.writerow(['客户触发', '我方回复'])
        
        seen_pairs = set()
        count = 0
        original_count = 0
        
        for row in reader:
            original_count += 1
            q = refine_text(row.get('客户触发', ''), is_question=True)
            a = refine_text(row.get('我方回复', ''), is_question=False)
            
            if is_valuable(q, a):
                pair_key = (q, a)
                if pair_key not in seen_pairs:
                    writer.writerow([q, a])
                    seen_pairs.add(pair_key)
                    count += 1
                    
    print(f"Finalization complete.")
    print(f"Original pairs: {original_count}")
    print(f"Refined unique pairs: {count}")

if __name__ == "__main__":
    finalize_kb(r"d:\items\QW\docs\企微提取内容_processed.csv", 
                r"d:\items\QW\docs\企微知识库_final.csv")
