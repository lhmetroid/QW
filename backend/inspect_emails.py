import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

def load_env(p):
    if not os.path.exists(p): return
    for l in open(p):
        l = l.strip()
        if not l or l.startswith('#') or '=' not in l: continue
        k, v = l.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())
load_env(os.path.join(os.path.dirname(__file__), '..', '.env'))

from database import engine, EmailThreadAsset
from sqlalchemy import text, or_, and_
from sqlalchemy.orm import sessionmaker

Session = sessionmaker(bind=engine)
session = Session()

# Total emails
total_count = session.query(EmailThreadAsset).count()
print(f"Total rows in email_thread_asset: {total_count}")

# Check null / empty
empty_subject_or_content = session.query(EmailThreadAsset).filter(
    or_(
        EmailThreadAsset.subject == None,
        EmailThreadAsset.subject == '',
        EmailThreadAsset.content == None,
        EmailThreadAsset.content == ''
    )
).count()
print(f"Empty subject or content (NULL or empty string): {empty_subject_or_content}")

# Test emails: let's see how many subject or content contains 'test' (case insensitive)
test_count = session.query(EmailThreadAsset).filter(
    or_(
        EmailThreadAsset.subject.ilike('%test%'),
        EmailThreadAsset.content.ilike('%test%')
    )
).count()
print(f"Contains 'test' (case-insensitive) in subject or content: {test_count}")

# Let's inspect some of the 'test' emails to see what they look like
test_samples = session.query(EmailThreadAsset).filter(
    or_(
        EmailThreadAsset.subject.ilike('%test%'),
        EmailThreadAsset.content.ilike('%test%')
    )
).limit(10).all()

print("\n--- Samples of 'test' emails ---")
for i, item in enumerate(test_samples):
    print(f"Sample {i+1}:")
    print(f"  ID: {item.email_id}")
    print(f"  Subject: {item.subject}")
    print(f"  Content snippet: {item.content[:100]}")
    print(f"  usable_for_reply: {item.usable_for_reply}")
    print(f"  allowed_for_generation: {item.allowed_for_generation}")
    print(f"  status: {item.status}")
    print(f"  source_type: {item.source_type}")
    print(f"  source_ref: {item.source_ref}")

session.close()
