import os
import csv

def run_evaluation(router):
    print("Running evaluation on dataset/sample_messages.csv...")
    
    # Load sample messages
    sample_path = os.path.join(router.dataset_dir, 'sample_messages.csv')
    if not os.path.exists(sample_path):
        print(f"Error: Sample messages file not found at {sample_path}")
        return

    samples = []
    with open(sample_path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        samples = list(reader)

    print(f"Loaded {len(samples)} sample messages.")

    correct_action = 0
    correct_type = 0
    total = len(samples)

    mismatches = []

    for msg in samples:
        # Create a clean message dict without the answer keys to prevent leaking
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

        # Predict
        prediction = router.route_message(clean_msg)

        true_action = msg['action']
        true_type = msg['message_type']
        
        pred_action = prediction.get('action')
        pred_type = prediction.get('message_type')

        is_action_ok = pred_action == true_action
        is_type_ok = pred_type == true_type

        if is_action_ok:
            correct_action += 1
        if is_type_ok:
            correct_type += 1

        if not is_action_ok or not is_type_ok:
            mismatches.append({
                "message_id": msg['message_id'],
                "text": msg['message_text'][:60] + "...",
                "true_action": true_action,
                "pred_action": pred_action,
                "true_type": true_type,
                "pred_type": pred_type,
                "reason": prediction.get('reason')
            })

    action_accuracy = correct_action / total if total > 0 else 0.0
    type_accuracy = correct_type / total if total > 0 else 0.0

    print("\n" + "="*40)
    print(" EVALUATION RESULTS")
    print("="*40)
    print(f"Action Triage Accuracy:     {action_accuracy:.2%} ({correct_action}/{total})")
    print(f"Message Type Classification: {type_accuracy:.2%} ({correct_type}/{total})")
    print("="*40)

    if mismatches:
        print(f"\nSample Mismatches (showing first 5 of {len(mismatches)}):")
        for m in mismatches[:5]:
            print(f"- ID: {m['message_id']}")
            print(f"  Text: {m['text']}")
            print(f"  Expected: Action={m['true_action']}, Type={m['true_type']}")
            print(f"  Predicted: Action={m['pred_action']}, Type={m['pred_type']}")
            print(f"  Rule Reason: {m['reason']}")
            print()
    else:
        print("\nPerfect match on all sample cases!")

if __name__ == "__main__":
    # Test evaluation directly if run as main
    from main import MessageRouter
    router = MessageRouter('dataset')
    run_evaluation(router)
