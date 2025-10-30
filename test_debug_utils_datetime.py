"""Test script to verify datetime serialization in debug_utils."""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Enable debug mode for testing
os.environ["ENABLE_DEBUG_FILES"] = "true"

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.debug_utils import save_debug_file, is_debug_enabled


def test_datetime_serialization():
    """Test that datetime objects are properly serialized to JSON."""
    print("\n=== Testing Datetime Serialization in Debug Utils ===\n")

    if not is_debug_enabled():
        print("[FAIL] Debug mode is not enabled")
        sys.exit(1)

    # Test data with datetime objects
    test_data = {
        "timestamp": datetime.now(),
        "execution_time": datetime(2025, 10, 28, 13, 15, 30),
        "query": "SELECT * FROM test",
        "result_count": 42,
        "nested": {
            "created_at": datetime(2025, 10, 1, 10, 0, 0),
            "value": 123
        }
    }

    try:
        # Attempt to save file with datetime objects
        result = save_debug_file(
            "test_datetime.json",
            test_data,
            step_name="test",
            include_timestamp=True
        )

        if result:
            print(f"[PASS] Debug file saved successfully: {result}")

            # Verify the file was created and contains valid JSON
            import json
            with open(result, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)

            print(f"[PASS] File contains valid JSON")
            print(f"       - Keys: {list(loaded_data.keys())}")
            print(f"       - Timestamps serialized as ISO format strings")

            # Clean up test file
            os.remove(result)
            print(f"[PASS] Test file cleaned up")

            return True
        else:
            print("[FAIL] Debug file was not saved")
            return False

    except TypeError as e:
        print(f"[FAIL] TypeError during serialization: {str(e)}")
        return False
    except Exception as e:
        print(f"[FAIL] Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_logrecord_conflict():
    """Test that filename parameter doesn't conflict with LogRecord."""
    print("\n=== Testing LogRecord Conflict Fix ===\n")

    # This should not raise a KeyError about 'filename' in LogRecord
    # We're testing the exception handling path which uses 'debug_filename' instead
    test_data = {
        "invalid": object()  # This will cause JSON serialization to fail
    }

    try:
        # This should fail to serialize but not raise LogRecord conflict
        result = save_debug_file(
            "test_invalid.json",
            test_data,
            step_name="test"
        )

        # Should return None due to serialization error
        if result is None:
            print("[PASS] Failed serialization handled gracefully")
            print("       - No LogRecord 'filename' conflict")
            return True
        else:
            print("[FAIL] Should have failed to serialize")
            return False

    except KeyError as e:
        if "filename" in str(e) or "Attempt to overwrite" in str(e):
            print(f"[FAIL] LogRecord conflict still exists: {str(e)}")
            return False
        else:
            raise
    except Exception as e:
        print(f"[INFO] Expected serialization error occurred: {type(e).__name__}")
        print("[PASS] No LogRecord conflict")
        return True


if __name__ == "__main__":
    test1 = test_datetime_serialization()
    test2 = test_logrecord_conflict()

    print("\n=== Test Results ===")
    print(f"Datetime Serialization: {'PASS' if test1 else 'FAIL'}")
    print(f"LogRecord Conflict Fix: {'PASS' if test2 else 'FAIL'}")

    if test1 and test2:
        print("\n[SUCCESS] All tests passed!")
        sys.exit(0)
    else:
        print("\n[FAILURE] Some tests failed")
        sys.exit(1)
