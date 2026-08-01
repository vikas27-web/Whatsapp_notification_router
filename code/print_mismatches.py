import os
import csv
from main import MessageRouter

router = MessageRouter('dataset')
sample_path = os.path.join('dataset', 'sample_messages.csv')
with open(sample_path, encoding='utf-8-sig') as f:
    samples = list(csv.DictReader(f))

mismatches = []
for msg in samples:
    clean_msg = {k: msg[k] for k in ['message_id', 'user_id', 'conversation_type', 'group_id', 'business_id', 'sender_user_id', 'created_at', 'message_text', 'media_type', 'media_id', 'forwarded_count']}
    pred = router.route_message(clean_msg)
    if pred['action'] != msg['action'] or pred['message_type'] != msg['message_type']:
        mismatches.append((msg, pred))

print(f"Total mismatches: {len(mismatches)} / {len(samples)}")
for msg, pred in mismatches:
    print(f"ID: {msg['message_id']} | Text: {(msg['message_text'] or '')[:40]}")
    print(f"  EXPECTED : Action={msg['action']}, Type={msg['message_type']}")
    print(f"  PREDICTED: Action={pred['action']}, Type={pred['message_type']}")
    print(f"  Reason: {pred['reason']}\n")
