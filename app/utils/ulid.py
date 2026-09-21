import time
from datetime import datetime
from typing import Optional, Union
import ulid


def generate_ulid(
    timestamp: Optional[
        Union[int, float, str, bytes, bytearray, memoryview, datetime]
    ] = None,
) -> str:
    if timestamp is None:
        timestamp = time.time()
    return str(ulid.from_timestamp(timestamp))
