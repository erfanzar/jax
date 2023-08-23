# Copyright 2020 The JAX Authors.
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

from __future__ import annotations

from jax import numpy as jnp
from jax._src import array
from jax._src import xla_bridge
from jax._src.lib import xla_client
from jax._src.lib import xla_extension_version
from jax._src.typing import Array


SUPPORTED_DTYPES = frozenset({
    jnp.int8, jnp.int16, jnp.int32, jnp.int64, jnp.uint8, jnp.uint16,
    jnp.uint32, jnp.uint64, jnp.float16, jnp.bfloat16, jnp.float32,
    jnp.float64, jnp.complex64, jnp.complex128})


def to_dlpack(x: Array, take_ownership: bool = False,
              stream: int | None = None):
  """Returns a DLPack tensor that encapsulates a :class:`~jax.Array` ``x``.

  Takes ownership of the contents of ``x``; leaves ``x`` in an invalid/deleted
  state.

  Args:
    x: a :class:`~jax.Array`, on either CPU or GPU.
    take_ownership: If ``True``, JAX hands ownership of the buffer to DLPack,
      and the consumer is free to mutate the buffer; the JAX buffer acts as if
      it were deleted. If ``False``, JAX retains ownership of the buffer; it is
      undefined behavior if the DLPack consumer writes to a buffer that JAX
      owns.
    stream: optional platform-dependent stream to wait on until the buffer is
      ready. This corresponds to the `stream` argument to ``__dlpack__``
      documented in https://dmlc.github.io/dlpack/latest/python_spec.html.
  """
  if not isinstance(x, array.ArrayImpl):
    raise TypeError("Argument to to_dlpack must be a jax.Array, "
                    f"got {type(x)}")
  assert len(x.devices()) == 1
  if xla_extension_version >= 186:
    return xla_client._xla.buffer_to_dlpack_managed_tensor(
        x.addressable_data(0), take_ownership=take_ownership, stream=stream
    )  # type: ignore
  else:
    if stream is not None:
      raise ValueError(
          "passing `stream` argument to to_dlpack requires jaxlib >= 0.4.15")
    return xla_client._xla.buffer_to_dlpack_managed_tensor(
        x.addressable_data(0), take_ownership=take_ownership)  # type: ignore



def from_dlpack(dlpack):
  """Returns a :class:`~jax.Array` representation of a DLPack tensor.

  The returned :class:`~jax.Array` shares memory with ``dlpack``.

  Args:
    dlpack: a DLPack tensor, on either CPU or GPU.
  """
  cpu_backend = xla_bridge.get_backend("cpu")
  try:
    gpu_backend = xla_bridge.get_backend("cuda")
  except RuntimeError:
    gpu_backend = None

  # Try ROCm if CUDA backend not found
  if gpu_backend is None:
    try:
      gpu_backend = xla_bridge.get_backend("rocm")
    except RuntimeError:
      gpu_backend = None

  return jnp.asarray(xla_client._xla.dlpack_managed_tensor_to_buffer(
      dlpack, cpu_backend, gpu_backend))
