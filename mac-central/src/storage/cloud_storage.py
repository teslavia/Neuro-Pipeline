"""Cloud storage client for uploading keyframes and artifacts.

Supports S3-compatible storage (AWS S3, MinIO). Lazy-loads boto3
and degrades gracefully if not installed.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


class CloudStorageClient:
    """Async S3-compatible upload client with graceful degradation."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "neuro-pipeline/",
        endpoint_url: str = "",
        region: str = "us-east-1",
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix
        self.endpoint_url = endpoint_url
        self.region = region
        self._client = None
        self._available = False
        self._init_client()

    def _init_client(self) -> None:
        try:
            import boto3
            kwargs = {"region_name": self.region}
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url
            self._client = boto3.client("s3", **kwargs)
            self._available = True
            logger.info(f"CloudStorage initialized: bucket={self.bucket}")
        except ImportError:
            logger.warning("boto3 not installed, cloud storage disabled")
        except (OSError, ConnectionError) as e:
            logger.error(f"Failed to init cloud storage: {e}")

    @property
    def available(self) -> bool:
        return self._available

    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        content_type: str = "application/octet-stream",
        metadata: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """Upload bytes to S3. Returns the full key on success, None on failure."""
        if not self._available:
            return None
        full_key = f"{self.prefix}{key}"
        loop = asyncio.get_event_loop()
        try:
            put_kwargs = {
                "Bucket": self.bucket,
                "Key": full_key,
                "Body": data,
                "ContentType": content_type,
            }
            if metadata:
                put_kwargs["Metadata"] = metadata
            await loop.run_in_executor(
                _executor,
                lambda: self._client.put_object(**put_kwargs),
            )
            logger.info(f"Uploaded {len(data)} bytes to s3://{self.bucket}/{full_key}")
            return full_key
        except (OSError, ConnectionError) as e:
            logger.error(f"Upload failed: {e}")
            return None

    async def upload_frame(
        self,
        frame_data: bytes,
        device_id: str,
        frame_id: int,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """Upload a JPEG keyframe with structured key."""
        key = f"frames/{device_id}/{frame_id}.jpg"
        return await self.upload_bytes(
            frame_data, key, content_type="image/jpeg", metadata=metadata
        )
