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

"""Shorthand for `Checkpointer(PyTreeCheckpointHandler())`."""

from orbax.checkpoint import checkpointer
from orbax.checkpoint import pytree_checkpoint_handler


class PyTreeCheckpointer(checkpointer.Checkpointer):
  """Shorthand class.

  Instead of::
    ckptr = Checkpointer(PyTreeCheckpointHandler())

  we can use::
    ckptr = PyTreeCheckpointer()
  """

  def __init__(self, primary_host: int = 0, use_ocdbt: bool = True):
    super().__init__(
        pytree_checkpoint_handler.PyTreeCheckpointHandler(use_ocdbt=use_ocdbt),
        primary_host=primary_host,
    )
