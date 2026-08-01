import os
import csv
from main import MessageRouter

router = MessageRouter('dataset')
sample_path = os.path.join('dataset', 'sample_messages.csv')
with open(sample_path, encoding='utf-8-sig') as f:
    samples = list(csv.DictReader(f))

total = len(samples)
action_correct = 0
type_correct = 0
scam_correct = 0
scam_total = 0
evidence_matches = 0
evidence_total = 0
confidences = []

for msg in samples:
    clean_msg = {k: msg[k] for k in ['message_id', 'user_id', 'conversation_type', 'group_id', 'business_id', 'sender_user_id', 'created_at', 'message_text', 'media_type', 'media_id', 'forwarded_count']}
    pred = router.route_message(clean_msg)
    
    if pred['action'] == msg['action']:
        action_correct += 1
    if pred['message_type'] == msg['message_type']:
        type_correct += 1
        
    if msg['message_type'] in ['scam', 'spam']:
        scam_total += 1
        if pred['action'] == 'mute' and pred['message_type'] in ['scam', 'spam']:
            scam_correct += 1

    if msg['evidence_message_ids'] != 'none':
        evidence_total += 1
        if pred['evidence_message_ids'] != 'none':
            evidence_matches += 1

    confidences.append(float(pred['confidence']))

print("="*50)
print(" GRANULAR SYSTEM ACCURACY & METRICS REPORT")
print("="*50)
print(f"1. Action Triage Accuracy:       {action_correct/total:.2%} ({action_correct}/{total})")
print(f"2. Message Type Classification:   {type_correct/total:.2%} ({type_correct}/{total})")
print(f"3. Scam / Fraud Detection Recall: {scam_correct/scam_total:.2%} ({scam_correct}/{scam_total})")
print(f"4. Evidence Retrieval Rate:       {evidence_matches/evidence_total:.2%} ({evidence_matches}/{evidence_total})")
print(f"5. Average Confidence Score:     {sum(confidences)/len(confidences):.2f}")
print("="*50)
