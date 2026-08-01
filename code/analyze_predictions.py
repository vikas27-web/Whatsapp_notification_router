import os
import csv
from main import MessageRouter

def analyze():
    router = MessageRouter('dataset')
    sample_path = os.path.join(router.dataset_dir, 'sample_messages.csv')
    if not os.path.exists(sample_path):
        print(f"Error: Sample messages file not found at {sample_path}")
        return

    with open(sample_path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        samples = list(reader)

    print(f"Loaded {len(samples)} samples.\n")
    print(f"{'ID':<15} | {'True Act':<8} | {'Pred Act':<8} | {'True Type':<15} | {'Pred Type':<15} | {'Match'}")
    print("-" * 80)

    mismatches = []
    matches = []

    for msg in samples:
        clean_msg = {
            "message_id": msg['message_id'],
            "user_id": msg['user_id'],
            "conversation_type": msg['conversation_type'],
            "group_id": msg['group_id'],
            "business_id": msg['business_id'],
            "sender_user_id": msg['sender_user_id'],
            "created_at": msg['created_at'],
            "message_text": msg['message_text'],
            "media_type": msg['media_type'],
            "media_id": msg['media_id'],
            "forwarded_count": msg['forwarded_count']
        }
        
        prediction = router.route_message(clean_msg)
        
        true_action = msg['action']
        true_type = msg['message_type']
        pred_action = prediction.get('action')
        pred_type = prediction.get('message_type')
        reason = prediction.get('reason')
        
        act_ok = true_action == pred_action
        type_ok = true_type == pred_type
        all_ok = act_ok and type_ok
        
        status = "OK" if all_ok else "FAIL"
        print(f"{msg['message_id']:<15} | {true_action:<8} | {pred_action:<8} | {true_type:<15} | {pred_type:<15} | {status}")
        
        item = {
            "msg": msg,
            "pred_action": pred_action,
            "pred_type": pred_type,
            "reason": reason,
            "all_ok": all_ok,
            "act_ok": act_ok,
            "type_ok": type_ok
        }
        if all_ok:
            matches.append(item)
        else:
            mismatches.append(item)

    print(f"\nSummary: {len(matches)} OK, {len(mismatches)} FAIL out of {len(samples)}")
    
    print("\n" + "="*80)
    print(" DETAILED FAILURES")
    print("="*80)
    for idx, item in enumerate(mismatches):
        msg = item['msg']
        print(f"\n[{idx+1}] ID: {msg['message_id']} | Conv Type: {msg['conversation_type']}")
        print(f"Text: {repr(msg['message_text'])}")
        print(f"Media Type: {msg['media_type']} | Media ID: {msg['media_id']}")
        print(f"Expected: Action={msg['action']}, Type={msg['message_type']}")
        print(f"Predicted: Action={item['pred_action']}, Type={item['pred_type']}")
        print(f"Reason: {item['reason']}")
        
        # Get context to see what rules checked
        ctx_msg = {
            "message_id": msg['message_id'],
            "user_id": msg['user_id'],
            "conversation_type": msg['conversation_type'],
            "group_id": msg['group_id'],
            "business_id": msg['business_id'],
            "sender_user_id": msg['sender_user_id'],
            "created_at": msg['created_at'],
            "message_text": msg['message_text'],
            "media_type": msg['media_type'],
            "media_id": msg['media_id'],
            "forwarded_count": msg['forwarded_count']
        }
        ctx = router.dl.get_message_context(ctx_msg)
        print("Context values of interest:")
        if msg['conversation_type'] == 'group':
            print(f"  Group Muted: {ctx.get('group_membership', {}).get('group_muted_by_user')}")
            print(f"  Sender Role: {ctx.get('sender_membership', {}).get('role')}")
            print(f"  Group Type: {ctx.get('group', {}).get('group_type')}")
        elif msg['conversation_type'] == 'business':
            print(f"  Official Domain: {ctx.get('business', {}).get('official_domain')}")
            print(f"  Domain Used: {ctx.get('business', {}).get('domain_used_by_sender')}")
            print(f"  Why User Knows: {ctx.get('user_business_history', {}).get('why_user_knows_account')}")
            print(f"  Opt Out: {ctx.get('user_business_history', {}).get('promotions_opted_out_at')}")
        elif msg['conversation_type'] == 'personal':
            print(f"  Sender ID: {msg['sender_user_id']}")
            print(f"  History Precedents Count: {len(ctx.get('history', []))}")
        print(f"  User DND: {ctx.get('user', {}).get('do_not_disturb_window')}")
        print(f"  User Fatigue: {ctx.get('user_fatigue')}")

if __name__ == '__main__':
    analyze()
