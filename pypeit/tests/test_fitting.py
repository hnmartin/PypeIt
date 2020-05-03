"""
Module to run tests on fitting
"""
import sys
import io
import os
import shutil
import inspect

from IPython import embed

import pytest

import numpy as np

from pypeit.core import fitting

def data_path(filename):
    data_dir = os.path.join(os.path.dirname(__file__), 'files')
    return os.path.join(data_dir, filename)

def test_pypeitfit():
    out_file = data_path('test_fit.fits')
    if os.path.isfile(out_file):
        os.remove(out_file)
    pypeitFit = fitting.PypeItFit(fitc=np.arange(100).astype(float))
    # Write
    pypeitFit.to_file(out_file)
    # Read
    pypeitFit2 = fitting.PypeItFit.from_file(out_file)
    assert np.array_equal(pypeitFit.fitc, pypeitFit2.fitc)
    pypeitFit2.to_file(out_file, overwrite=True)
    # Finish
    os.remove(out_file)


def test_polynomial():
    """ Run the parameter setup script
    """
    x = np.pi*np.linspace(0, 1., 100)
    y = np.sin(x)
    # Polynomial
    pypeitFit = fitting.func_fit(x, y, 'polynomial', 3)
    np.testing.assert_allclose(pypeitFit.fitc, np.array([ -4.74660344e-02,   1.30745471e+00,
                                                  -4.16175760e-01, 3.08557167e-18]), atol=1e-9)

def test_legendre():
    x = np.pi*np.linspace(0, 1., 100)
    y = np.sin(x)
    # Legendre
    pypeitFit = fitting.func_fit(x, y, 'legendre', 3)
    np.testing.assert_allclose(pypeitFit.fitc, np.array([  6.37115652e-01,   6.83317251e-17,
                                                   -6.84581686e-01, -7.59352737e-17]), atol=1e-9)

