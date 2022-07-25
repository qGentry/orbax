# Copyright 2022 The Orbax Authors.
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

"""Common tests for AbstractCheckpointManager subclasses."""
from absl.testing import parameterized
from flax import linen as nn
from flax.training.train_state import TrainState
import jax
from jax.experimental import multihost_utils
from jax.experimental import pjit
from jax.experimental.maps import Mesh
import jax.numpy as jnp
import numpy as np
import optax
from orbax.checkpoint import AsyncCheckpointer
from orbax.checkpoint import PyTreeCheckpointHandler
from orbax.checkpoint import RestoreArgs
from orbax.checkpoint import test_utils
import tensorflow as tf

PyTree = type(jax.tree_structure(None))
jax.config.update('jax_parallel_functions_output_gda', True)


class CheckpointerTestBase:
  """Common tests for AbstractCheckpointer subclasses."""

  class Test(parameterized.TestCase):
    """Structure allows test to run as subclasses, not base class."""

    def checkpointer(self, handler):
      raise NotImplementedError

    def setUp(self):
      super().setUp()
      pytree, mesh_tree, axes_tree = test_utils.setup_gda_pytree()
      doubled_pytree = test_utils.apply_function(pytree, lambda x: x * 2)

      self.empty_pytree = jax.tree_map(
          lambda x: object(), pytree, is_leaf=test_utils.is_leaf)
      self.pytree = pytree
      self.doubled_pytree = doubled_pytree
      self.mesh_tree = mesh_tree
      self.axes_tree = axes_tree
      self.pytree_restore_args = jax.tree_map(
          lambda mesh, axes: RestoreArgs(mesh=mesh, mesh_axes=axes),
          self.mesh_tree, self.axes_tree)
      self.dataset = tf.data.Dataset.range(64)
      self.directory = self.create_tempdir(name='checkpointing_test').full_path
      self.directory = tf.io.gfile.join(self.directory, 'ckpt')

      multihost_utils.sync_global_devices('CheckpointerTest:setup_complete')

    def tearDown(self):
      multihost_utils.sync_global_devices('CheckpointerTest:tests_complete')
      super().tearDown()

    def wait_if_async(self, checkpointer):
      if isinstance(checkpointer, AsyncCheckpointer):
        checkpointer.wait_until_finished()

    def test_save_restore(self):
      """Basic save and restore test."""
      checkpointer = self.checkpointer(PyTreeCheckpointHandler())
      checkpointer.save(self.directory, self.pytree)
      self.wait_if_async(checkpointer)
      restored = checkpointer.restore(
          self.directory, restore_args=self.pytree_restore_args)
      test_utils.assert_tree_equal(self, self.pytree, restored)

    def test_save_restore_no_kwargs(self):
      """Restore with no GDA args."""
      checkpointer = self.checkpointer(PyTreeCheckpointHandler())
      checkpointer.save(self.directory, self.pytree)
      self.wait_if_async(checkpointer)
      restored = checkpointer.restore(self.directory)
      expected = jax.tree_map(test_utils.replicate_gda, self.pytree)
      expected = jax.tree_map(lambda x: np.asarray(x.local_data(0)), expected)
      test_utils.assert_tree_equal(self, expected, restored)

    def test_restore_missing_path(self):
      """Restore with invalid item."""
      checkpointer = self.checkpointer(PyTreeCheckpointHandler())
      with self.assertRaises(FileNotFoundError):
        checkpointer.restore('path/to/missing')

    def test_save_structure(self):
      checkpointer = self.checkpointer(PyTreeCheckpointHandler())
      checkpointer.save(self.directory, self.pytree)
      self.wait_if_async(checkpointer)
      structure = checkpointer.structure(self.directory)
      handler = PyTreeCheckpointHandler()
      expected = checkpointer.structure(handler.structure(self.directory))
      test_utils.assert_tree_equal(self, expected, structure)

    def test_no_overwrite_existing(self):
      """Test same step does not overwrite."""
      checkpointer = self.checkpointer(PyTreeCheckpointHandler())
      checkpointer.save(self.directory, self.pytree)
      self.wait_if_async(checkpointer)
      with self.assertRaises(ValueError):
        checkpointer.save(self.directory, self.doubled_pytree)
      self.wait_if_async(checkpointer)
      restored = checkpointer.restore(
          self.directory, restore_args=self.pytree_restore_args)
      expected = self.pytree
      test_utils.assert_tree_equal(self, expected, restored)

    def test_overwrite_existing(self):
      """Test same step does not overwrite."""
      checkpointer = self.checkpointer(PyTreeCheckpointHandler())
      checkpointer.save(self.directory, self.pytree)
      self.wait_if_async(checkpointer)
      checkpointer.save(self.directory, self.doubled_pytree, force=True)
      self.wait_if_async(checkpointer)
      restored = checkpointer.restore(
          self.directory, restore_args=self.pytree_restore_args)
      expected = self.doubled_pytree
      test_utils.assert_tree_equal(self, expected, restored)

    def test_flax_train_state(self):
      """Test using flax model."""

      class MLP(nn.Module):
        """A simple MLP model."""

        @nn.compact
        def __call__(self, x: jnp.ndarray) -> jnp.ndarray:
          x = x.reshape((x.shape[0], -1))  # flatten
          x = nn.Dense(features=8)(x)
          return x

      model = MLP()
      mesh = Mesh(np.asarray(jax.devices()), ('devices',))
      mesh_axes = pjit.PartitionSpec()

      @jax.jit
      def init_state():
        params = model.init(jax.random.PRNGKey(0), jnp.ones([8, 8]))
        tx = optax.adamw(learning_rate=0.001)
        state = TrainState.create(apply_fn=model.apply, params=params, tx=tx)
        return state

      init = pjit.pjit(
          init_state, in_axis_resources=None, out_axis_resources=mesh_axes)

      with Mesh(mesh.devices, mesh.axis_names):
        state = init()
        state_shape = jax.eval_shape(init)

      restore_args = jax.tree_map(
          lambda _: RestoreArgs(mesh=mesh, mesh_axes=mesh_axes), state_shape)

      checkpointer = self.checkpointer(PyTreeCheckpointHandler())
      checkpointer.save(self.directory, state)
      self.wait_if_async(checkpointer)
      # Already fully replicated, don't need to provide args.
      restored = checkpointer.restore(
          self.directory, item=state_shape, restore_args=restore_args)
      test_utils.assert_tree_equal(self, state.params, restored.params)
      test_utils.assert_tree_equal(self, state.opt_state, restored.opt_state)