import csv
import os
import re
import sys
import traceback
from datetime import datetime

def clean_content(text):
    if not text:
        return ""
    
    # Handle Quote format (Standard Reply)
    # Example: 这是一条引用/回复消息：\n“Name：\nContent”\n------\nReply
    quote_match = re.search(r"这是一条引用/回复消息：\s*“[^：\s]+：\s*(.*?)”\s*------\s*(.*)", text, re.DOTALL)
    if quote_match:
        content = quote_match.group(1).strip()
        reply = quote_match.group(2).strip()
        # Clean the inner content too (might be media)
        content = clean_content(content)
        return f"引用：{content}；回复：{reply}"
    
    # Handle another quote format: 「Name：Content」\n- - - - - - - - - - - - - - -\nReply
    quote_match2 = re.search(r"「[^：\s]+：\s*(.*?)」\s*- - - - - - - - - - - - - - -\s*(.*)", text, re.DOTALL)
    if quote_match2:
        content = quote_match2.group(1).strip()
        reply = quote_match2.group(2).strip()
        content = clean_content(content)
        return f"引用：{content}；回复：{reply}"

    # Standardize media placeholders
    text = text.replace("【未知消息类型】", "[图片/文件/语音]")
    text = text.replace("【图片】", "[图片]")
    text = text.replace("【语音】", "[语音]")
    text = text.replace("【文件】", "[文件]")
    text = text.replace("【视频】", "[视频]")
    
    # Handle Video Channel shares
    if "来自视频号" in text and "的视频" in text:
        text = "[视频号]"

    return text.strip()

def process_csv(input_file, output_file, log_file):
    print(f"Starting processing: {input_file}")
    
    encodings = ['utf-8-sig', 'gbk', 'utf-16']
    reader = None
    f_in = None
    
    for enc in encodings:
        try:
            f_in = open(input_file, mode='r', encoding=enc)
            # Peek at the header
            line = f_in.readline()
            if '发件人' in line or '收件人' in line:
                f_in.seek(0)
                reader = csv.DictReader(f_in)
                print(f"Using encoding: {enc}")
                break
            f_in.close()
        except Exception:
            if f_in: f_in.close()
            continue
            
    if not reader:
        print("Error: Could not determine file encoding or format.")
        return

    f_out = open(output_file, mode='w', encoding='utf-8-sig', newline='')
    writer = csv.writer(f_out)
    writer.writerow(['客户触发', '我方回复'])
    
    f_log = open(log_file, mode='w', encoding='utf-8')
    
    current_dialogue_id = None
    q_buffer = []
    a_buffer = []
    last_role = None # 'customer' or 'sales'
    
    line_count = 0
    success_count = 0
    fail_count = 0
    
    last_time = None
    
    try:
        for row in reader:
            line_count += 1
            if line_count % 10000 == 0:
                print(f"Processed {line_count} lines...")

            sender = row.get('发件人', '')
            content = row.get('内容', '')
            time_str = row.get('时间', '')
            from_id = row.get('from', '')
            to_id = row.get('tolist', '')
            group_id = row.get('群ID', '')

            # Parse time
            current_time = None
            if time_str:
                try:
                    # Expected format: 2024/12/3 15:28:06
                    current_time = datetime.strptime(time_str, '%Y/%m/%d %H:%M:%S')
                except:
                    pass

            # Empty row indicates dialogue end
            if not sender and not content:
                if q_buffer and a_buffer:
                    writer.writerow(["\n".join(q_buffer), "\n".join(a_buffer)])
                    success_count += 1
                q_buffer = []
                a_buffer = []
                last_role = None
                current_dialogue_id = None
                last_time = None
                continue

            role = None
            if sender.startswith('客户:'):
                role = 'customer'
            elif sender.startswith('销售:'):
                role = 'sales'
            
            if not role:
                continue

            did = group_id if group_id else "-".join(sorted([from_id, to_id]))
            
            # Day break rule: If same dialogue and same role, but different day, flush and reset
            is_new_day = False
            if last_time and current_time:
                if last_time.date() != current_time.date():
                    is_new_day = True

            if (current_dialogue_id and did != current_dialogue_id) or is_new_day:
                # Flush existing pair if complete
                if q_buffer and a_buffer:
                    writer.writerow(["\n".join(q_buffer), "\n".join(a_buffer)])
                    success_count += 1
                q_buffer = []
                a_buffer = []
                # If it's just a new day in the same dialogue, we keep the dialogue ID but treat buffers as new start
                if is_new_day and did == current_dialogue_id:
                    # Reset last_role to prevent merging across days even if same person
                    last_role = None 
            
            current_dialogue_id = did
            last_time = current_time
            
            cleaned = clean_content(content)
            if not cleaned:
                continue

            if role == 'customer':
                if last_role == 'sales':
                    if q_buffer and a_buffer:
                        writer.writerow(["\n".join(q_buffer), "\n".join(a_buffer)])
                        success_count += 1
                        q_buffer = []
                        a_buffer = []
                q_buffer.append(cleaned)
                last_role = 'customer'
            else: # sales
                if last_role == 'customer' or last_role == 'sales':
                    a_buffer.append(cleaned)
                    last_role = 'sales'

        # Final flush
        if q_buffer and a_buffer:
            writer.writerow(["\n".join(q_buffer), "\n".join(a_buffer)])
            success_count += 1
            
    except Exception as e:
        fail_count += 1
        f_log.write(f"Error at line {line_count}: {str(e)}\n")
        f_log.write(traceback.format_exc())
        print(f"Error encountered at line {line_count}. Check {log_file} for details.")
    finally:
        f_in.close()
        f_out.close()
        f_log.close()
        
    print(f"Processing complete.")
    print(f"Total lines read: {line_count}")
    print(f"Successful pairs: {success_count}")
    print(f"Failures recorded: {fail_count}")

if __name__ == "__main__":
    input_path = r"d:\items\QW\docs\企微提取内容_20260509111157.csv"
    output_path = r"d:\items\QW\docs\企微提取内容_processed.csv"
    log_path = r"d:\items\QW\docs\process_log.txt"
    
    process_csv(input_path, output_path, log_path)
