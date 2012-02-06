# Copyright 2011, Vinothan N. Manoharan, Thomas G. Dimiduk, Rebecca
# W. Perry, Jerome Fung, and Ryan McGorty
#
# This file is part of Holopy.
#
# Holopy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Holopy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Holopy.  If not, see <http://www.gnu.org/licenses/>.
"""
Compute holograms using the discrete dipole approximation (DDA).  Currently uses
ADDA (http://code.google.com/p/a-dda/) to do DDA calculations.

.. moduleauthor:: Thomas G. Dimiduk <tdimiduk@physics.harvard.edu>
"""

#TODO: Adda currently fails if you call it with things specified in meters
#(values are too small), so we should probably nondimensionalize before talking
#to adda.  

import subprocess
import tempfile
import shutil
import glob
import os
import numpy as np
#from numpy.testing import assert_allclose
import holopy as hp
from .scatteringtheory import ScatteringTheory, ElectricField
from .mie_f import mieangfuncs


class DependencyMissing(Exception):
    def __init__(self, dep):
        self.dep = dep
    def __str__(self):
        return "External Dependency: " + self.dep + " could not be found.  Is \
it installed and configured properly?"

class DDA(ScatteringTheory):
    """
    Scattering theory class that calculates holograms using the Discrete Dipole
    Approximation (DDA).  Can in principle handle any scatterer

    Attributes
    ----------
    imshape : float or tuple (optional)
        Size of grid to calculate scattered fields or
        intensities. This is the shape of the image that calc_field or
        calc_intensity will return
    phis : array 
        Specifies azimuthal scattering angles to calculate (incident
        direction is z)
    thetas : array 
        Specifies polar scattering angles to calculate
    optics : :class:`holopy.optics.Optics` object
        specifies optical train    

    Notes
    -----
    Does not handle near fields.  This introduces ~5% error at 10 microns.
    
    This can in principle handle any scatterer, but in practice it will need
    excessive memory or computation time for particularly large scatterers.  
    """
    def __init__(self, optics, imshape=(256,256), thetas=None, phis=None):
        # Check that adda is present and able to run
        try:
            subprocess.check_output(['adda', '-V'])
        except (subprocess.CalledProcessError, OSError):
            raise DependencyMissing('adda')

        super(DDA, self).__init__(optics, imshape, thetas, phis)

    def _write_adda_angles_file(self, theta, phi, kr, temp_dir):
        # adda expects degrees, so convert
        angles = np.vstack((theta, phi)).transpose() * 180/np.pi
        # Leave filename hardcoded for now since it is the default name for adda
        outf = file(os.path.join(temp_dir, 'scat_params.dat'), 'w')

        # write the header on the scattering angles file
        header = """global_type=pairs
N={0}
pairs=
""".format(len(phi))
        outf.write(header)
        # Now write all the angles
        np.savetxt(outf, angles)
        outf.close()

    def calc_holo(self, scatterer, alpha=1.0):
        temp_dir = tempfile.mkdtemp()
        
        grid = self._spherical_grid(*scatterer.center)
        theta = grid[...,1].ravel()
        phi = grid[...,2].ravel()
        kr = grid[...,0].ravel()

        self._write_adda_angles_file(theta, phi, kr, temp_dir)
        
        # TODO, have it actually look at the scatterer

        
        # TODO: this only works for spheres at the moment
        subprocess.check_call(['adda', '-scat_matr', 'ampl', '-store_scat_grid',
                               '-lambda', str(self.optics.med_wavelen),
                               '-eq_rad', str(scatterer.r), '-m',
                               str(scatterer.n.real/self.optics.index),
                               str(scatterer.n.imag/self.optics.index)],
                              cwd=temp_dir)
        
        # Go into the results directory, there should only be one run
        result_dir = glob.glob(os.path.join(temp_dir, 'run000*'))[0]

        adda_result = np.loadtxt(os.path.join(result_dir, 'ampl_scatgrid'),
                                 skiprows=1)
        # columns in result are
        # theta phi s1.r s1.i s2.r s2.i s3.r s3.i s4.r s4.i
        
        out_theta = adda_result[:,0]
        out_phi = adda_result[:,1]

        # Sanity check that the output angles are the same as the input ones
        # need relatively loose tolerances because adda appears to round off the
        # values we give it.  This may be a problem later, we will have to see
#        assert_allclose(out_theta, theta, rtol=.1)
#        assert_allclose(out_phi, phi, rtol=.5)
        # TODO: kr will not line up perfectly with the angles things were
        # actually calculated at, need to figure out which sets of coordinates
        # to use.  
        
        # Combine the real and imaginary components from the file into complex
        # numbers
        s = adda_result[:,2::2] + 1.0j*adda_result[:,3::2]

        # Now arrange them into a scattering matrix, see Bohren and Huffman p63
        # eq 3.12
        scat_matr = np.array([[s[:,1], s[:,2]], [s[:,3], s[:,0]]]).transpose()
        # TODO: check normalization

        
        #shutil.rmtree(temp_dir)
        print(temp_dir)
        
        pixels = np.zeros_like(kr)
        for i in range(len(kr)):
            pixels[i] = mieangfuncs.paraxholocl(kr[i], scatterer.z *
                                                self.optics.wavevec,
                                                theta[i], phi[i], scat_matr[i],
                                                self.optics.polarization, alpha)

        return hp.Hologram(pixels.reshape(self.imshape), optics = self.optics)

#        prefactor = 1.0j/kr*np.exp(1e0j*kr)
#        prefactor = prefactor.reshape(prefactor.size, 1)
#        signarr = 1.0 - 1.0j # needed since escatperp = -escatphi
#        escatsph = prefactor*np.tensordot(scat_matr,self.optics.polarization, axes=1)*signarr

        ct = np.cos(theta)
        st = np.sin(theta)
        cp = np.cos(phi)
        sp = np.sin(phi)        

        e_x = ct*cp*escatsph[:,0] - sp*escatsph[:,1]
        e_y = ct*sp*escatsph[:,0] + cp*escatsph[:,1]
        e_z = -1.0*st*escatsph[:,0]

        e_x = e_x.reshape(self.imshape)
        e_y = e_y.reshape(self.imshape)
        e_z = e_z.reshape(self.imshape)

        return ElectricField(e_x, e_y, e_z, 0, self.optics.med_wavelen)

        
