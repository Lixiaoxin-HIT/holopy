# Copyright 2011-2016, Vinothan N. Manoharan, Thomas G. Dimiduk,
# Rebecca W. Perry, Jerome Fung, and Ryan McGorty, Anna Wang
#
# This file is part of HoloPy.
#
# HoloPy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HoloPy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HoloPy.  If not, see <http://www.gnu.org/licenses/>.

from holopy.core.tests.common import assert_pickle_roundtrip, get_example_data

from holopy.inference.noise_model import AlphaModel
from holopy.inference import prior
from holopy.scattering.scatterer import Sphere
from holopy.scattering.theory import Mie

import numpy as np

def test_prior():
    g = prior.Gaussian(1, 1)
    assert_pickle_roundtrip(g)
    assert_pickle_roundtrip(g.lnprob)

def test_AlphaModelholo_likelihood():
    holo = get_example_data('image0001')
    s = Sphere(prior.Gaussian(.5, .1), prior.Gaussian(1.6, .1),
               (prior.Gaussian(5, 1), prior.Gaussian(5, 1), prior.Gaussian(5, 1)))
    model = AlphaModel(s, alpha = prior.Gaussian(.7, .1), noise_sd=.01)
    assert_pickle_roundtrip(model)
