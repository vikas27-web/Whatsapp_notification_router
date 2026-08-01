import os
import csv
import zipfile
from main import MessageRouter
from evaluation_helper import run_evaluation

def run_full_system_test():
    print("="*60)
    print(" RUNNING COMPLETE END-TO-END SYSTEM TEST SUITE")
    print("="*60)

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dataset_dir = os.path.join(repo_root, 'dataset')

    # Test 1: Data Loader Initialization & Media Cache
    print("\n[TEST 1/5] Testing Data Loader & Media Cache Loading...")
    router = MessageRouter(dataset_dir)
    assert len(router.dl.users) > 0, "Users table failed to load"
    assert len(router.dl.groups) > 0, "Groups table failed to load"
    assert len(router.dl.business_accounts) > 0, "Business accounts table failed to load"
    assert len(router.dl.message_history) > 0, "Message history table failed to load"
    assert len(router.media_cache) > 0, "Media cache failed to load"
    print(" -> PASS: All dataset tables and media cache loaded successfully.")

    # Test 2: Sample Evaluation Benchmark Test
    print("\n[TEST 2/5] Running Benchmark Evaluation on sample_messages.csv...")
    run_evaluation(router)
    print(" -> PASS: Evaluation benchmark execution completed cleanly.")

    # Test 3: Batch Processing Messages Test
    print("\n[TEST 3/5] Running Batch Inference on dataset/messages.csv...")
    input_path = os.path.join(dataset_dir, 'messages.csv')
    output_path = os.path.join(dataset_dir, 'output.csv')
    
    router.process_all('messages.csv', 'output.csv')
    assert os.path.exists(output_path), "output.csv was not created!"
    print(f" -> PASS: Batch inference finished. Output generated at {output_path}.")

    # Test 4: Schema & Output Validation
    print("\n[TEST 4/5] Validating output.csv Schema & Value Constraints...")
    input_msgs = router.dl._read_csv('messages.csv')
    output_rows = router.dl._read_csv('output.csv')

    assert len(input_msgs) == len(output_rows), f"Row count mismatch! Input has {len(input_msgs)}, output has {len(output_rows)}"
    
    valid_actions = {'notify', 'digest', 'mute'}
    valid_types = {'personal', 'urgent', 'event', 'payment', 'business_update', 'promotion', 'greeting', 'forward', 'spam', 'scam', 'unknown'}

    for idx, row in enumerate(output_rows):
        assert 'message_id' in row, f"Missing message_id at row {idx}"
        assert 'action' in row, f"Missing action at row {idx}"
        assert 'message_type' in row, f"Missing message_type at row {idx}"
        assert 'reason' in row, f"Missing reason at row {idx}"
        assert 'confidence' in row, f"Missing confidence at row {idx}"
        assert 'evidence_message_ids' in row, f"Missing evidence_message_ids at row {idx}"

        assert row['action'] in valid_actions, f"Invalid action '{row['action']}' at row {idx}"
        assert row['message_type'] in valid_types, f"Invalid message_type '{row['message_type']}' at row {idx}"
        
        try:
            conf = float(row['confidence'])
            assert 0.0 <= conf <= 1.0, f"Confidence {conf} out of bounds at row {idx}"
        except ValueError:
            raise AssertionError(f"Invalid float confidence '{row['confidence']}' at row {idx}")

        assert len(row['reason'].strip()) > 0, f"Empty reason at row {idx}"
        assert len(row['evidence_message_ids'].strip()) > 0, f"Empty evidence_message_ids at row {idx}"

    print(f" -> PASS: All {len(output_rows)} rows strictly adhere to output schema and value constraints.")

    # Test 5: Deliverables & Submission Packaging
    print("\n[TEST 5/5] Testing Submission Packaging (output.csv & code.zip)...")
    code_zip = os.path.join(repo_root, 'code.zip')
    root_output = os.path.join(repo_root, 'output.csv')

    # Execute packager
    import package_submission
    
    assert os.path.exists(code_zip), "code.zip not found in root"
    assert os.path.exists(root_output), "output.csv not found in root"

    with zipfile.ZipFile(code_zip, 'r') as z:
        names = z.namelist()
        assert any('main.py' in n for n in names), "code.zip missing main.py entry point"

    print(" -> PASS: Submission deliverables (code.zip and output.csv) verified.")

    print("\n" + "="*60)
    print(" ALL END-TO-END TESTS PASSED SUCCESSFULLY! SUBMISSION READY!")
    print("="*60)

if __name__ == "__main__":
    run_full_system_test()
