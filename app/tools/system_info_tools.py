import json
import os
import platform

import psutil

from app.schemas.tools import EmptyArgs
from app.tools.base import ReadOnlyTool


class GetLocalSystemInfoTool(ReadOnlyTool):
    input_model = EmptyArgs

    def __init__(self, timeout_seconds: int) -> None:
        super().__init__(name="get_local_system_info", description="Read safe local system information.", timeout_seconds=timeout_seconds)

    def execute(self, arguments: EmptyArgs, settings) -> str:
        return json.dumps(
            {
                "os_name": platform.system(),
                "os_version": platform.version(),
                "python_version": platform.python_version(),
                "architecture": platform.machine(),
                "logical_cpu_count": os.cpu_count(),
                "total_ram_bytes": int(psutil.virtual_memory().total),
                "application_version": settings.app_version,
            },
            ensure_ascii=False,
        )
