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
Reading and writing of yaml files.

yaml files are structured text files designed to be easy for humans to
read and write but also easy for computers to read.  Holopy uses them
to store information about experimental conditions and to describe
analysis procedures.

.. moduleauthor:: Tom Dimiduk <tdimiduk@physics.harvard.edu>
"""
from __future__ import division
try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict
import numpy as np
import yaml
import re
import inspect
import types
from ..holopy_object import SerializableMetaclass
from ..data import Data
from .. import data

class LoadError(Exception):
    def __init__(self, msg):
        self.msg = msg
    def __str__(self):
        return self.msg

def save(outf, obj):
    if isinstance(outf, basestring):
        outf = file(outf, 'w')

    yaml.dump(obj, outf)
    if isinstance(obj, Data):
        # yaml saves of large arrays are very slow, so we have numpy save the data
        # parts of data objects.  This will mean the file isn't stricktly
        # a valid yaml (or even a valid text file really), but we can still read
        # it, and with the right programs (like linux more) you can still see
        # the text yaml information, and it keeps everything in one file
        outf.write('array: !NpyBinary\n')
        np.save(outf, obj)
            

def load(inf):
    if isinstance(inf, basestring):
        inf = file(inf)

    line = inf.readline()
    cls = line.strip('{} !\n')
    lines = []
    if hasattr(data, cls) and issubclass(getattr(data, cls), Data):
        while not re.search('!NpyBinary', line):
            lines.append(line)
            line = inf.readline()
        arr = np.load(inf)
        head = ''.join(lines[1:])
        kwargs = yaml.load(head)
        if kwargs is None:
            kwargs = {}
        return getattr(data, cls)(arr, **kwargs)


    else:
        inf.seek(0)
        obj = yaml.load(inf)
        if isinstance(obj, dict):
            # sometimes yaml doesn't convert strings to floats properly, so we
            # have to check for that.  
            for key in obj:
                if isinstance(obj[key], basestring):
                    try:
                        obj[key] = float(obj[key])
                    except ValueError:
                        pass
                
        return obj


###################################################################
# Custom Yaml Representers
###################################################################

# Represent 1d ndarrays as lists in yaml files because it makes them much
# prettier
def ndarray_representer(dumper, data):
    return dumper.represent_list(data.tolist())
yaml.add_representer(np.ndarray, ndarray_representer)

# represent tuples as lists because yaml doesn't have tuples
def tuple_representer(dumper, data):
    return dumper.represent_list(list(data))
yaml.add_representer(tuple, tuple_representer)

# represent numpy types as things that will print more cleanly
def complex_representer(dumper, data):
    return dumper.represent_scalar('!complex', repr(data.tolist()))
yaml.add_representer(np.complex128, complex_representer)
def complex_constructor(loader, node):
    return complex(node.value)
yaml.add_constructor('!complex', complex_constructor)

def numpy_float_representer(dumper, data):
    return dumper.represent_float(float(data))
yaml.add_representer(np.float64, numpy_float_representer)

def numpy_int_representer(dumper, data):
    return dumper.represent_int(int(data))
yaml.add_representer(np.int64, numpy_int_representer)

def class_representer(dumper, data):
    return dumper.represent_scalar('!class', "{0}.{1}".format(data.__module__,
                                                              data.__name__))
yaml.add_representer(SerializableMetaclass, class_representer)

def class_loader(loader, node):
    name = loader.construct_scalar(node)        
    tok = name.split('.')
    mod = __import__(tok[0])
    for t in tok[1:]:
        mod = mod.__getattribute__(t)
    return mod
yaml.add_constructor(u'!theory', class_loader)

def OrderedDict_representer(dumper, data):
    return dumper.represent_dict(data)
yaml.add_representer(OrderedDict, OrderedDict_representer)

def instancemethod_representer(dumper, data):
    func = data.im_func.func_name
    obj = data.im_self
    if isinstance(obj, SerializableMetaclass):
        obj = obj()
    return dumper.represent_scalar('!method', "{0} of {1}".format(func, yaml.dump(obj)))
yaml.add_representer(types.MethodType, instancemethod_representer)

def instancemethod_constructor(loader, node):
    name = loader.construct_scalar(node)
    tok = name.split('of')
    method = tok[0].strip()
    obj = 'dummy: '+ tok[1] 
    obj = yaml.load(obj)['dummy']
    return getattr(obj, method)
yaml.add_constructor('!method', instancemethod_constructor)

# legacy loader, this is only here because for a while we saved things as
# !Minimizer {algorithm = nmpfit} and we still want to be able to read those yamls
def minimizer_constructor(loader, node):
    data = loader.construct_mapping(node, deep=True)
    if data['algorithm'] == 'nmpfit':
        return Nmpfit()
    else:
        raise LoadError('Could not load Minimizer with: {0}'.format(data))
yaml.add_constructor("!Minimizer", minimizer_constructor)

def function_representer(dumper, data):
    code = inspect.getsource(data)
    code = code.split('\n',)
    # first line will be function name, we don't want that
    code = code[1].strip()
    return dumper.represent_scalar('!function', code)
# here I refer to function_representer.__class__ because I am not sure how else
# to access the type of a fuction (function does not work)
yaml.add_representer(function_representer.__class__, function_representer)

# for now punt if we attempt to read in functions. 
# make_scatterer in model is allowed to be any function, so we may encounter
# them.  This constructor allows the read to succeed, but the function will be
# absent.  
# It is possible to read in functions from the file, but it is more than a
# little subtle and kind of dangrous, so I want to think more about it before
# doing it - tgd 2012-06-4
def function_constructor(loader, node):
    return None
yaml.add_constructor('!function', function_constructor)


