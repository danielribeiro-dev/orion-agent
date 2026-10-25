"""
O.R.I.O.N — Native primitive tools.

Five surgical OS-interaction tools, each returning a RuntimeResult.
"""

from orion.runtime.tools.edit_file import EditFileTool
from orion.runtime.tools.read_file import ReadFileTool
from orion.runtime.tools.run_command import RunCommandTool
from orion.runtime.tools.search_files import SearchFilesTool
from orion.runtime.tools.write_file import WriteFileTool

__all__ = [
    "RunCommandTool",
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "SearchFilesTool",
]
