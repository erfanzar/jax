# Copyright 2023 The JAX Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for jax.numpy.ufunc and its methods."""

from functools import partial

from absl.testing import absltest

import numpy as np
import jax
import jax.numpy as jnp
from jax._src import test_util as jtu

from jax import config
config.parse_flags_with_absl()
FLAGS = config.FLAGS


def scalar_add(x, y):
  assert np.shape(x) == np.shape(y) == ()
  return x + y


def scalar_div(x, y):
  assert np.shape(x) == np.shape(y) == ()
  return x / y


def scalar_mul(x, y):
  assert np.shape(x) == np.shape(y) == ()
  return x * y


def scalar_sub(x, y):
  assert np.shape(x) == np.shape(y) == ()
  return x - y


SCALAR_FUNCS = [
  {'func': scalar_add, 'nin': 2, 'nout': 1, 'identity': 0},
  {'func': scalar_div, 'nin': 2, 'nout': 1, 'identity': None},
  {'func': scalar_mul, 'nin': 2, 'nout': 1, 'identity': 1},
  {'func': scalar_sub, 'nin': 2, 'nout': 1, 'identity': None},
]

broadcast_compatible_shapes = [(), (1,), (3,), (1, 3), (4, 1), (4, 3)]
nonscalar_shapes = [(3,), (4,), (4, 3)]

def cast_outputs(fun):
  def wrapped(*args, **kwargs):
    dtype = np.asarray(args[0]).dtype
    return jax.tree_map(lambda x: np.asarray(x, dtype=dtype), fun(*args, **kwargs))
  return wrapped


class LaxNumpyUfuncTests(jtu.JaxTestCase):

  @jtu.sample_product(SCALAR_FUNCS)
  def test_ufunc_properties(self, func, nin, nout, identity):
    jnp_fun = jnp.frompyfunc(func, nin=nin, nout=nout, identity=identity)
    self.assertEqual(jnp_fun.identity, identity)
    self.assertEqual(jnp_fun.nin, nin)
    self.assertEqual(jnp_fun.nout, nout)
    self.assertEqual(jnp_fun.nargs, nin)

  @jtu.sample_product(SCALAR_FUNCS)
  def test_ufunc_properties_readonly(self, func, nin, nout, identity):
    jnp_fun = jnp.frompyfunc(func, nin=nin, nout=nout, identity=identity)
    for attr in ['nargs', 'nin', 'nout', 'identity', '_func', '_call']:
      getattr(jnp_fun, attr)  # no error on attribute access.
      with self.assertRaises(AttributeError):
        setattr(jnp_fun, attr, None)  # error when trying to mutate.

  @jtu.sample_product(SCALAR_FUNCS)
  def test_ufunc_hash(self, func, nin, nout, identity):
    jnp_fun = jnp.frompyfunc(func, nin=nin, nout=nout, identity=identity)
    jnp_fun_2 = jnp.frompyfunc(func, nin=nin, nout=nout, identity=identity)
    self.assertEqual(jnp_fun, jnp_fun_2)
    self.assertEqual(hash(jnp_fun), hash(jnp_fun_2))

    other_fun = jnp.frompyfunc(jnp.add, nin=2, nout=1, identity=0)
    self.assertNotEqual(jnp_fun, other_fun)
    # Note: don't test hash for non-equality because it may collide.

  @jtu.sample_product(
      SCALAR_FUNCS,
      lhs_shape=broadcast_compatible_shapes,
      rhs_shape=broadcast_compatible_shapes,
      dtype=jtu.dtypes.floating,
  )
  def test_call(self, func, nin, nout, identity, lhs_shape, rhs_shape, dtype):
    jnp_fun = jnp.frompyfunc(func, nin=nin, nout=nout, identity=identity)
    np_fun = cast_outputs(np.frompyfunc(func, nin=nin, nout=nout, identity=identity))

    rng = jtu.rand_default(self.rng())
    args_maker = lambda: [rng(lhs_shape, dtype), rng(rhs_shape, dtype)]

    self._CheckAgainstNumpy(jnp_fun, np_fun, args_maker)
    self._CompileAndCheck(jnp_fun, args_maker)

  @jtu.sample_product(
      SCALAR_FUNCS,
      lhs_shape=broadcast_compatible_shapes,
      rhs_shape=broadcast_compatible_shapes,
      dtype=jtu.dtypes.floating,
  )
  def test_outer(self, func, nin, nout, identity, lhs_shape, rhs_shape, dtype):
    if (nin, nout) != (2, 1):
      self.skipTest(f"outer requires (nin, nout)=(2, 1); got {(nin, nout)=}")
    jnp_fun = jnp.frompyfunc(func, nin=nin, nout=nout, identity=identity).outer
    np_fun = cast_outputs(np.frompyfunc(func, nin=nin, nout=nout, identity=identity).outer)

    rng = jtu.rand_default(self.rng())
    args_maker = lambda: [rng(lhs_shape, dtype), rng(rhs_shape, dtype)]

    self._CheckAgainstNumpy(jnp_fun, np_fun, args_maker)
    self._CompileAndCheck(jnp_fun, args_maker)

  @jtu.sample_product(
      SCALAR_FUNCS,
      [{'shape': shape, 'axis': axis}
       for shape in nonscalar_shapes
       for axis in [None, *range(-len(shape), len(shape))]],
      dtype=jtu.dtypes.floating,
  )
  def test_reduce(self, func, nin, nout, identity, shape, axis, dtype):
    if (nin, nout) != (2, 1):
      self.skipTest(f"reduce requires (nin, nout)=(2, 1); got {(nin, nout)=}")
    jnp_fun = partial(jnp.frompyfunc(func, nin=nin, nout=nout, identity=identity).reduce, axis=axis)
    np_fun = cast_outputs(partial(np.frompyfunc(func, nin=nin, nout=nout, identity=identity).reduce, axis=axis))

    rng = jtu.rand_default(self.rng())
    args_maker = lambda: [rng(shape, dtype)]

    self._CheckAgainstNumpy(jnp_fun, np_fun, args_maker)
    self._CompileAndCheck(jnp_fun, args_maker, check_cache_misses=False)  # TODO(jakevdp): why the cache misses?

  @jtu.sample_product(
      SCALAR_FUNCS,
      [{'shape': shape, 'axis': axis}
       for shape in nonscalar_shapes
       for axis in range(-len(shape), len(shape))],
      dtype=jtu.dtypes.floating,
  )
  def test_accumulate(self, func, nin, nout, identity, shape, axis, dtype):
    if (nin, nout) != (2, 1):
      self.skipTest(f"accumulate requires (nin, nout)=(2, 1); got {(nin, nout)=}")
    jnp_fun = partial(jnp.frompyfunc(func, nin=nin, nout=nout, identity=identity).accumulate, axis=axis)
    np_fun = cast_outputs(partial(np.frompyfunc(func, nin=nin, nout=nout, identity=identity).accumulate, axis=axis))

    rng = jtu.rand_default(self.rng())
    args_maker = lambda: [rng(shape, dtype)]

    self._CheckAgainstNumpy(jnp_fun, np_fun, args_maker)
    self._CompileAndCheck(jnp_fun, args_maker)

  @jtu.sample_product(
      SCALAR_FUNCS,
      shape=nonscalar_shapes,
      idx_shape=[(), (2,)],
      dtype=jtu.dtypes.floating,
  )
  def test_at(self, func, nin, nout, identity, shape, idx_shape, dtype):
    if (nin, nout) != (2, 1):
      self.skipTest(f"accumulate requires (nin, nout)=(2, 1); got {(nin, nout)=}")
    jnp_fun = partial(jnp.frompyfunc(func, nin=nin, nout=nout, identity=identity).at, inplace=False)
    def np_fun(x, idx, y):
      x_copy = x.copy()
      np.frompyfunc(func, nin=nin, nout=nout, identity=identity).at(x_copy, idx, y)
      return x_copy

    rng = jtu.rand_default(self.rng())
    idx_rng = jtu.rand_int(self.rng(), low=-shape[0], high=shape[0])
    args_maker = lambda: [rng(shape, dtype), idx_rng(idx_shape, 'int32'), rng(idx_shape[1:], dtype)]

    self._CheckAgainstNumpy(jnp_fun, np_fun, args_maker)
    self._CompileAndCheck(jnp_fun, args_maker)

  @jtu.sample_product(
      SCALAR_FUNCS,
      [{'shape': shape, 'axis': axis}
       for shape in nonscalar_shapes
       for axis in [*range(-len(shape), len(shape))]],
      idx_shape=[(0,), (3,), (5,)],
      dtype=jtu.dtypes.floating,
  )
  def test_reduceat(self, func, nin, nout, identity, shape, axis, idx_shape, dtype):
    if (nin, nout) != (2, 1):
      self.skipTest(f"accumulate requires (nin, nout)=(2, 1); got {(nin, nout)=}")
    jnp_fun = partial(jnp.frompyfunc(func, nin=nin, nout=nout, identity=identity).reduceat, axis=axis)
    np_fun = cast_outputs(partial(np.frompyfunc(func, nin=nin, nout=nout, identity=identity).reduceat, axis=axis))

    rng = jtu.rand_default(self.rng())
    idx_rng = jtu.rand_int(self.rng(), low=0, high=shape[axis])
    args_maker = lambda: [rng(shape, dtype), idx_rng(idx_shape, 'int32')]

    self._CheckAgainstNumpy(jnp_fun, np_fun, args_maker)
    self._CompileAndCheck(jnp_fun, args_maker)


if __name__ == "__main__":
  absltest.main(testLoader=jtu.JaxTestLoader())
