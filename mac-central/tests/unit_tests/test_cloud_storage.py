"""Tests for CloudStorageClient."""

import pytest
from unittest.mock import MagicMock, patch

from src.storage.cloud_storage import CloudStorageClient


class TestCloudStorageClient:
    def test_unavailable_without_boto3(self):
        with patch.dict("sys.modules", {"boto3": None}):
            # Force reimport
            import importlib
            from src.storage import cloud_storage
            importlib.reload(cloud_storage)
            client = cloud_storage.CloudStorageClient(bucket="test")
            assert not client.available

    def test_available_with_mock_boto3(self):
        mock_boto3 = MagicMock()
        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            import importlib
            from src.storage import cloud_storage
            importlib.reload(cloud_storage)
            client = cloud_storage.CloudStorageClient(bucket="test")
            assert client.available

    @pytest.mark.asyncio
    async def test_upload_bytes_when_unavailable(self):
        client = CloudStorageClient(bucket="test")
        client._available = False
        result = await client.upload_bytes(b"data", "key.bin")
        assert result is None

    @pytest.mark.asyncio
    async def test_upload_bytes_success(self):
        client = CloudStorageClient(bucket="test")
        client._available = True
        client._client = MagicMock()
        result = await client.upload_bytes(b"data", "key.bin")
        assert result == "neuro-pipeline/key.bin"

    @pytest.mark.asyncio
    async def test_upload_frame(self):
        client = CloudStorageClient(bucket="test")
        client._available = True
        client._client = MagicMock()
        result = await client.upload_frame(b"\xff\xd8", "edge-001", 42)
        assert result == "neuro-pipeline/frames/edge-001/42.jpg"
