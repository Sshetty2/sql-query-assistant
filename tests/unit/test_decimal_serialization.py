"""Test that Decimal objects can be serialized in debug utils."""

import json
from decimal import Decimal
from datetime import datetime
from utils.debug_utils import DateTimeEncoder


def test_datetime_encoder_handles_decimal():
    """Test that DateTimeEncoder can serialize Decimal objects to float."""
    data = {
        'price': Decimal('99.99'),
        'score': Decimal('9.8'),
        'rating': Decimal('4.5')
    }

    # Should not raise an exception
    json_str = json.dumps(data, cls=DateTimeEncoder)
    parsed = json.loads(json_str)

    # Verify Decimals were converted to floats
    assert isinstance(parsed['price'], float)
    assert parsed['price'] == 99.99
    assert parsed['score'] == 9.8
    assert parsed['rating'] == 4.5


def test_datetime_encoder_handles_datetime():
    """Test that DateTimeEncoder can serialize datetime objects."""
    now = datetime(2025, 10, 30, 14, 30, 0)
    data = {'timestamp': now}

    json_str = json.dumps(data, cls=DateTimeEncoder)
    parsed = json.loads(json_str)

    # Verify datetime was converted to ISO string
    assert isinstance(parsed['timestamp'], str)
    assert parsed['timestamp'] == '2025-10-30T14:30:00'


def test_datetime_encoder_handles_mixed_types():
    """Test that DateTimeEncoder can handle Decimal, datetime, and regular types together."""
    data = {
        'id': 123,
        'name': 'Test',
        'score': Decimal('9.8'),
        'timestamp': datetime(2025, 10, 30, 14, 30, 0),
        'active': True
    }

    json_str = json.dumps(data, cls=DateTimeEncoder)
    parsed = json.loads(json_str)

    assert parsed['id'] == 123
    assert parsed['name'] == 'Test'
    assert parsed['score'] == 9.8
    assert isinstance(parsed['score'], float)
    assert parsed['timestamp'] == '2025-10-30T14:30:00'
    assert parsed['active'] is True


def test_datetime_encoder_handles_nested_decimals():
    """Test that DateTimeEncoder can handle nested structures with Decimals."""
    data = {
        'results': [
            {'id': 1, 'cvss': Decimal('9.8'), 'count': 3},
            {'id': 2, 'cvss': Decimal('7.5'), 'count': 2},
        ]
    }

    json_str = json.dumps(data, cls=DateTimeEncoder)
    parsed = json.loads(json_str)

    assert parsed['results'][0]['cvss'] == 9.8
    assert parsed['results'][1]['cvss'] == 7.5
    assert isinstance(parsed['results'][0]['cvss'], float)
