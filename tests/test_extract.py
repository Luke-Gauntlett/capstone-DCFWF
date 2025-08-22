import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import mock_open, patch, MagicMock
import os
import time


from src.extract.extract import (
    main,
    get_last_extraction_time,
    save_current_extraction_time,
    request_data,
    key,
    secret,
    url,
    last_extraction_file
)


@pytest.fixture(autouse=True)
def mock_all_globals(mocker):
    mocker.patch('os.getenv', side_effect={
        "consumer_key": "test_key",
        "consumer_secret": "test_secret",
    }.get)

    mocker.patch('src.extract.extract.key', "test_key")
    mocker.patch('src.extract.extract.secret', "test_secret")
    mocker.patch('src.extract.extract.url', "https://mock.url/wp-json/wc/v3")
    mocker.patch('src.extract.extract.last_extraction_file', "mock_data/last_extraction_time.json")
    mocker.patch('os.makedirs')


def test_get_last_extraction_time_success(mocker):
    mock_file_content = json.dumps({"last_extraction": "2023-01-01T10:00:00"})
    mocker.patch('builtins.open', mock_open(read_data=mock_file_content))
    mocker.patch('src.extract.extract.json.load', return_value={"last_extraction": "2023-01-01T10:00:00"})
    
    result = get_last_extraction_time()
    assert result == "2023-01-01T10:00:00"


def test_save_current_extraction_time_success(mocker):
    mock_file = mock_open()
    mocker.patch('builtins.open', mock_file)
    
    mock_json_dump = mocker.patch('src.extract.extract.json.dump')

    extraction_time = "2023-01-02T11:00:00"
    save_current_extraction_time(extraction_time)

    mock_file.assert_called_once_with("mock_data/last_extraction_time.json", "w")
    mock_json_dump.assert_called_once_with({"last_extraction": extraction_time}, mock_file())


def test_request_data_single_page_success(mocker):
    # Simulate a single page of data, followed by an empty list to stop pagination
    mock_response_page1 = MagicMock()
    mock_response_page1.json.return_value = [
        {
            "id": 123,
            "status": "processing",
            "total": "99.99",
            "billing": {"email": "john.doe@example.com"},
            "date_created": "2023-08-20T10:00:00"
        }
    ]
    mock_response_page1.raise_for_status.return_value = None

    mock_response_page2 = MagicMock()
    mock_response_page2.json.return_value = [] # This signals the end of pagination
    mock_response_page2.raise_for_status.return_value = None

    # Capture the mock object returned by mocker.patch
    mock_requests_get = mocker.patch('requests.get', side_effect=[mock_response_page1, mock_response_page2])
    # Mock time.sleep to prevent actual delays during the pagination loop
    mocker.patch('time.sleep', return_value=None) 

    data = request_data("orders", "")
    
    assert len(data) == 1
    assert data[0]["id"] == 123
    assert data[0]["status"] == "processing"
    # Use the captured mock object for assertions
    assert mock_requests_get.call_count == 2
    mock_requests_get.assert_any_call(
        "https://mock.url/wp-json/wc/v3/orders",
        auth=("test_key", "test_secret"),
        params={"per_page": 100, "page": 1, "status": "any"},
        timeout=60
    )
    mock_requests_get.assert_any_call(
        "https://mock.url/wp-json/wc/v3/orders",
        auth=("test_key", "test_secret"),
        params={"per_page": 100, "page": 2, "status": "any"}, # Should be called with page 2
        timeout=60
    )


def test_main_fetches_new_data_and_updates_time(mocker):
    # Capture the mock objects
    mock_get_last_extraction_time = mocker.patch('src.extract.extract.get_last_extraction_time', return_value="")
    mock_save_current_extraction_time = mocker.patch('src.extract.extract.save_current_extraction_time')
    mock_request_data = mocker.patch('src.extract.extract.request_data', return_value=[{"id": 101, "status": "processing", "total": "50.00"}])
    
    mock_datetime = MagicMock(wraps=datetime)
    now_time = datetime(2023, 1, 15, 10, 30, 0)
    mock_datetime.now.return_value = now_time
    mocker.patch('datetime.datetime', mock_datetime)

    result = main()

    assert result == [{"id": 101, "status": "processing", "total": "50.00"}]
    # Use the captured mock objects for assertions
    mock_get_last_extraction_time.assert_called_once()
    mock_request_data.assert_called_once_with("orders", "")
    
    expected_extraction_time = (now_time - timedelta(minutes=2)).isoformat()
    mock_save_current_extraction_time.assert_called_once_with(expected_extraction_time)


def test_main_no_new_data_no_time_update(mocker):
    previous_time = "2023-01-01T00:00:00"
    # Capture the mock objects
    mock_get_last_extraction_time = mocker.patch('src.extract.extract.get_last_extraction_time', return_value=previous_time)
    mock_save_current_extraction_time = mocker.patch('src.extract.extract.save_current_extraction_time')
    mock_request_data = mocker.patch('src.extract.extract.request_data', return_value=[])

    result = main()

    assert result == []
    # Use the captured mock objects for assertions
    mock_get_last_extraction_time.assert_called_once()
    mock_request_data.assert_called_once_with("orders", previous_time)
    mock_save_current_extraction_time.assert_not_called()
