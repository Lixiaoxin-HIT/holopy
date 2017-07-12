# Copyright 2011-2013, Vinothan N. Manoharan, Thomas G. Dimiduk,
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
"""
Compute holograms using Mishchenko's T-matrix method for axisymmetric scatterers.  Currently uses

.. moduleauthor:: Anna Wang <annawang@seas.harvard.edu>
"""

import numpy as np
import subprocess
import tempfile
import glob
import os
import shutil
from ..scatterer import Sphere, Axisymmetric
from ..errors import TheoryNotCompatibleError

from .scatteringtheory import ScatteringTheory
try:
    from .mie_f import mieangfuncs
except:
    pass

class Tmatrix(ScatteringTheory):
    """
    Computes scattering using the axisymmetric T-matrix solution by Mishchenko
    with extended precision.

    It can calculate scattering from axisymmetric scatterers. Calculations for
    particles which are very large and have high aspect ratios may not
    converge.

    This model requires an external scattering code:

    Attributes
    ----------
    delete : bool (optional)
        If true (default), delete the temporary directory where we store the
        input and output file for the fortran executable

    Notes
    -----
    Does not handle near fields.  This introduces ~5% error at 10 microns.

    """
    def __init__(self, delete=True):
        self.delete = delete
        super().__init__()

    def _can_handle(self, scatterer):
        return isinstance(scatterer, Sphere) or isinstance(scatterer, Axisymmetric)

    def _run_tmat(self, temp_dir):
        cmd = ['./S.exe']
        subprocess.check_call(cmd, cwd=temp_dir)
        return

    def _raw_scat_matrs(self, scatterer, pos, medium_wavevec, medium_index):
        temp_dir = tempfile.mkdtemp()
        current_directory = os.getcwd()
        path, _ = os.path.split(os.path.abspath(__file__))
        tmatrixlocation = os.path.join(path, 'tmatrix_f', 'S.exe')
        shutil.copy(tmatrixlocation, temp_dir)
        os.chdir(temp_dir)

        angles = pos[:, 1:] * 180/np.pi
        outf = open(os.path.join(temp_dir, 'tmatrix_tmp.inp'), 'wb')

        # write the info into the scattering angles file in the following order:

        med_wavelen = 2*np.pi/medium_wavevec
        if isinstance(scatterer, Sphere):
            outf.write((str(scatterer.r)+'\n').encode('utf-8'))
            outf.write((str(med_wavelen)+'\n').encode('utf-8'))
            outf.write((str(scatterer.n.real/medium_index)+'\n').encode('utf-8'))
            outf.write((str(scatterer.n.imag/medium_index)+'\n').encode('utf-8'))
            # aspect ratio is 1
            outf.write((str(1)+'\n').encode('utf-8'))
            outf.write((str(0)+'\n').encode('utf-8'))
            outf.write((str(0)+'\n').encode('utf-8'))
            # shape is -1 (spheroid)
            outf.write((str(-1)+'\n').encode('utf-8'))
            outf.write((str(angles.shape[0])+'\n').encode('utf-8'))
        elif isinstance(scatterer, Axisymmetric):
            if scatterer.shape == -1:
                outf.write((str((scatterer.r[1]*scatterer.r[0]**2)**(1/3.))+'\n').encode('utf-8'))
            if scatterer.shape == -2:
                outf.write((str((3/2.*scatterer.r[1]*scatterer.r[0]**2)**(1/3.))+'\n').encode('utf-8'))
            outf.write((str(med_wavelen)+'\n').encode('utf-8'))
            outf.write((str(scatterer.n.real/medium_index)+'\n').encode('utf-8'))
            outf.write((str(scatterer.n.imag/medium_index)+'\n').encode('utf-8'))
            outf.write((str(scatterer.r[0]/scatterer.r[1])+'\n').encode('utf-8'))
            outf.write((str(scatterer.rotation[1]*180/np.pi)+'\n').encode('utf-8'))
            outf.write((str(scatterer.rotation[0]*180/np.pi)+'\n').encode('utf-8'))
            outf.write((str(scatterer.shape)+'\n').encode('utf-8'))
            outf.write((str(angles.shape[0])+'\n').encode('utf-8'))
        else:
            # cleanup and raise error
            outf.close()
            shutil.rmtree(temp_dir)
            raise TheoryNotCompatibleError(self, scatterer)

        # Now write all the angles
        np.savetxt(outf, angles)
        outf.close()

        self._run_tmat(temp_dir)

        # Go into the results directory
        result_file = glob.glob(os.path.join(temp_dir, 'tmatrix_tmp.out'))[0]

        tmat_result = np.loadtxt(result_file)
        # columns in result are
        # s11.r s11.i s12.r s12.i s21.r s21.i s22.r s22.i
        # should be
        # s11 s12
        # s21 s22

        # Combine the real and imaginary components from the file into complex
        # numbers. Then scale by -ki due to Mishchenko's conventions in eq 5. of
        # Mishchenko, Applied Optics (2000).
        s = tmat_result[:,0::2] + 1.0j*tmat_result[:,1::2]
        s = s*(-2j*np.pi/med_wavelen)
        # Now arrange them into a scattering matrix, noting that Mishchenko's basis
        # vectors are different from the B/H, so we need to take that into account:
        scat_matr = np.array([[s[:,0], s[:,1]], [-s[:,2], -s[:,3]]]).transpose()

        os.chdir(current_directory)

        if self.delete:
            shutil.rmtree(temp_dir)

        return scat_matr

    def _raw_fields(self, pos, scatterer, medium_wavevec, medium_index, illum_polarization):
        pos = pos.T
        scat_matr = self._raw_scat_matrs(scatterer, pos, medium_wavevec=medium_wavevec, medium_index=medium_index)
        fields = np.zeros_like(pos, dtype = scat_matr.dtype)

        for i, point in enumerate(pos):
            kr, theta, phi = point
            # TODO: figure out why postfactor is needed -- it is not used in dda.py
            postfactor = np.array([[np.cos(phi),np.sin(phi)],[-np.sin(phi),np.cos(phi)]])
            escat_sph = mieangfuncs.calc_scat_field(kr, phi, np.dot(scat_matr[i],postfactor),
                                                    illum_polarization.values[:2])
            fields[i] = mieangfuncs.fieldstocart(escat_sph, theta, phi)
        return fields.T
