# Copyright 2021 Xanadu Quantum Technologies Inc.

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations
from abc import ABC, abstractmethod
import numpy as np

from mrmustard.physics import gaussian, fock
from mrmustard.physics.abstract.state import State
from mrmustard.utils.types import *
from mrmustard.utils import graphics
from mrmustard import settings



class Transformation(ABC):
    r"""
    Base class for all transformations.
    Note that measurements are CP but not TP, so they have their own abstract class.
    Transformations include:
        * unitary transformations
        * non-unitary CPTP channels
    """
    _bell = None  # single-mode TMSV state for gaussian to fock transformation
    is_unitary = True  # whether the transformation is unitary

    def __call__(self, state: State) -> State:
        if state.is_gaussian:
            return self.transform_gaussian(state)
        else:
            return self.transform_fock(state)

    @property
    def bell(self):
        if self._bell is None:
            cov = gaussian.two_mode_squeezed_vacuum_cov(np.float64(settings.TMSV_DEFAULT_R), np.float64(0.0), settings.HBAR)
            means = gaussian.vacuum_means(2, settings.HBAR)
            bell = bell_single = State.from_gaussian(cov=cov, means=means, mixed=False)
            for _ in self.modes[1:]:
                bell = bell & bell_single
            tot = 2*len(self.modes)
            order = tuple(range(0, tot, 2)) + tuple(range(1, tot, 2))
            self._bell = bell[order]
        return self._bell

    def transform_gaussian(self, state: State) -> State:
        r"""
        Transforms a Gaussian state.
        """
        d = self.d_vector
        X = self.X_matrix
        Y = self.Y_matrix
        cov, means = gaussian.CPTP(state.cov, state.means, X, Y, d, self.modes)
        return State.from_gaussian(cov, means, mixed=state.is_mixed or Y is not None)

    def transform_fock(self, state: State) -> State:
        r"""
        Transforms a Fock state.
        """
        transformation = self.fock(cutoffs = state.cutoffs + state.cutoffs if state.is_pure else state.cutoffs)
        new_state = fock.CPTP(transformation=transformation, state=state.fock, unitary=self.is_unitary, state_mixed=state.is_mixed)
        return State.from_fock(new_state, mixed=not self.is_unitary or state.is_mixed)

    def __repr__(self):
        with np.printoptions(precision=6, suppress=True):
            lst = [f"{name}={np.array(np.atleast_1d(self.__dict__[name]))}" for name in self.param_names]
            return f"{self.__class__.__qualname__}(modes={self.modes}, {', '.join(lst)})"

    @property
    def modes(self) -> Sequence[int]:
        if self._modes in (None, []):
            if (d := self.d_vector) is not None:
                self._modes = list(range(d.shape[-1] // 2))
            elif (X := self.X_matrix) is not None:
                self._modes = list(range(X.shape[-1] // 2))
            elif (Y := self.Y_matrix) is not None:
                self._modes = list(range(Y.shape[-1] // 2))
        return self._modes

    @modes.setter
    def modes(self, modes: List[int]):
        r"""
        Sets the modes of the input state.
        """
        self._validate_modes(modes)
        self._modes = modes

    def _validate_modes(self, modes):
        pass  # override as needed

    @property
    def X_matrix(self) -> Optional[Matrix]:
        return None

    @property
    def Y_matrix(self) -> Optional[Matrix]:
        return None

    @property
    def d_vector(self) -> Optional[Vector]:
        return None

    def fock(self, cutoffs: Sequence[int], reshaped: bool = False):
        unnormalized = self(self.bell).ket(cutoffs=cutoffs)
        return fock.normalize_choi_trick(unnormalized, settings.TMSV_DEFAULT_R)

    def trainable_parameters(self) -> Dict[str, List[Trainable]]:
        return {"symplectic": [], "orthogonal": [], "euclidean": self._trainable_parameters}

    def __getitem__(self, items) -> Callable:
        r"""
        Allows transformations to be used as:
        output = op[0,1](input)  # e.g. acting on modes 0 and 1
        """
        if isinstance(items, int):
            modes = [items]
        elif isinstance(items, slice):
            modes = list(range(items.start, items.stop, items.step))
        elif isinstance(items, (Sequence, Iterable)):
            modes = list(items)
        else:
            raise ValueError(f"{items} is not a valid slice or list of modes.")
        self.modes = modes
        return self
