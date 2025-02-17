# Copyright 2023 The Orbax Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""JsonCheckpointHandler class.

Implementation of CheckpointHandler interface.
"""
import dataclasses
import json
from typing import Any, Mapping, Optional

from etils import epath
import jax
from orbax.checkpoint import checkpoint_args
from orbax.checkpoint import checkpoint_handler

CheckpointArgs = checkpoint_args.CheckpointArgs
register_with_handler = checkpoint_args.register_with_handler


class JsonCheckpointHandler(checkpoint_handler.CheckpointHandler):
  """Saves nested dictionary using json."""

  def __init__(self, filename: Optional[str] = None):
    """Initializes JsonCheckpointHandler.

    Args:
      filename: optional file name given to the written file; defaults to
        'metadata'
    """
    self._filename = filename or 'metadata'

  def save(self, directory: epath.Path, item: Mapping[str, Any]):
    """Saves the given item.

    Args:
      directory: save location directory.
      item: nested dictionary.
    """
    if jax.process_index() == 0:
      path = directory / self._filename
      path.write_text(json.dumps(item))

  def restore(
      self, directory: epath.Path, item: Optional[bytes] = None
  ) -> bytes:
    """Restores json mapping from directory.

    `item` is unused.

    Args:
      directory: restore location directory.
      item: unused

    Returns:
      Binary data read from `directory`.
    """
    del item
    path = directory / self._filename
    return json.loads(path.read_text())

  def structure(self, directory: epath.Path) -> Any:
    """Unimplemented. See parent class."""
    return NotImplementedError


@register_with_handler(JsonCheckpointHandler)
@dataclasses.dataclass
class JsonSaveArgs(CheckpointArgs):
  """Parameters for saving to json.

  Attributes:
    item (required): a nested dictionary.
  """

  item: Mapping[str, Any]


@register_with_handler(JsonCheckpointHandler)
@dataclasses.dataclass
class JsonRestoreArgs(CheckpointArgs):
  """Json restore args.

  No attributes, but use this class to indicate that an item should be restored
  from json.
  """
