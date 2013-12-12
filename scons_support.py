#!/usr/bin/env python
#  This file is part of LOOS.
#
#  LOOS (Lightweight Object-Oriented Structure library)
#  Copyright (c) 2013, Tod D. Romo
#  Department of Biochemistry and Biophysics
#  School of Medicine & Dentistry, University of Rochester
#
#  This package (LOOS) is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation under version 3 of the License.
#
#  This package is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.


# This file contains support code for SCons for building LOOS

import sys
import os
import glob
import platform
import re
from subprocess import *
from time import strftime
import shutil
import distutils.sysconfig
import distutils.spawn
from string import Template
from distutils.version import LooseVersion

import SCons

import loos_build_config


# Attempt to canonicalize system name, type and other related info...
# Note: this exports to globals rather than being contained within the check framework.
def CheckSystemType(conf):
    conf.Message('Determining platform ...')
    loos_build_config.host_type = platform.system()

# Detect CYGWIN & canonicalize linux type, setting defaults...
    if (re.search("(?i)cygwin", loos_build_config.host_type)):
        loos_build_config.host_type = 'Cygwin'
        loos_build_config.suffix = 'dll.a'
    elif (loos_build_config.host_type == 'Linux'):
        # Determine linux variant...
        linux_type = platform.platform()
        
        if (re.search("(?i)ubuntu", linux_type)):
            linux_type = 'ubuntu'
        elif (re.search("(?i)suse", linux_type)):
            linux_type = 'suse'
        elif (re.search("(?i)debian", linux_type)):
            linux_type = 'debian'
        elif (re.search("(?i)centos", linux_type)):
            linux_type = 'centos'
        elif (re.search("(?i)fedora", linux_type)):
            linux_type = 'fedora'

        loos_build_config.linux_type = linux_type

    # MacOS is special (of course...)
    elif (loos_build_config.host_type == 'Darwin'):
        loos_build_config.suffix = 'dylib'

    typemsg = loos_build_config.host_type
    if (typemsg == 'Linux'):
        typemsg = typemsg + ' [' + loos_build_config.linux_type + ']'
        
    conf.Result(typemsg)




### Create a revision file for linking against.
def setupRevision(env):

    # Divine the current revision...
    revision = loos_build_config.loos_version + " " + strftime("%y%m%d")

    # Now, write this out to a cpp file that can be linked in...this avoids having
    # to recompile everything when building on a new date.  We also rely on SCons
    # using the MD5 checksum to detect changes in the file (even though it's always
    # rewritten)
    revfile = open('revision.cpp', 'w')
    revfile.write('#include <string>\n')
    revfile.write('std::string revision_label = "')
    revfile.write(revision)
    revfile.write('";\n')
    revfile.close()


### Let environment variables override or modify some build paramaters...
def environOverride(conf):
    # Allow overrides from environment...
    if 'CXX' in os.environ:
        conf.env.Replace(CXX = os.environ['CXX'])
        print '*** Using compiler ' + os.environ['CXX']
    
    if 'CCFLAGS' in os.environ:
        conf.env.Append(CCFLAGS = os.environ['CCFLAGS'])
        print '*** Appending custom build flags: ' + os.environ['CCFLAGS']
        
    if 'LDFLAGS' in os.environ:
        conf.env.Append(LINKFLAGS = os.environ['LDFLAGS'])
        print '*** Appending custom link flag: ' + os.environ['LDFLAGS']



### Builder for setup scripts

# This copies the environment setup script while changing the directory
# that's used for setting up PATH and [DY]LD_LIBRARY_PATH.  If LOOS
# is being built in a directory, the env script will be setup to use
# the built-in-place distribution.  If LOOS is being installed, then
# it will use the installation directory instead.

def script_builder_python(target, source, env):

   libpaths = env['LIBPATH']
   libpaths.pop(0)

   cpppaths = env['CPPPATH']
   cpppaths.pop(0)

   ldlibrary = loos_build_config.user_libdirs.values()

   if not 'install' in SCons.Script.COMMAND_LINE_TARGETS:
       toolpath = '$LOOS/Tools:' + ':'.join(['$LOOS/Packages/' + s for s in [loos_build_config.package_list[i] for i in loos_build_config.package_list]])
       loos_dir = env.Dir('.').abspath
       libpaths.insert(0, loos_dir)
       cpppaths.insert(0, loos_dir)
       ldlibrary.insert(0, loos_dir)
       loos_pythonpath = loos_dir

   else:
       loos_dir = env['PREFIX']
       toolpath = loos_dir + '/bin'
       libpaths.insert(0, loos_dir + '/lib')
       cpppaths.insert(0, loos_dir + '/include')
       ldlibrary.insert(0, loos_dir + '/lib')
       loos_pythonpath = loos_dir + '/lib'
       

   file = open(str(source[0]), 'r')
   script = file.read()
   script_template = Template(script)
   script = script_template.substitute(loos_path = loos_dir,
                                       tool_path = toolpath,
                                       libpath = ':'.join(libpaths),
                                       cpppath = ':'.join(cpppaths),
                                       linkflags = env['LINKFLAGS'],
                                       libs = ':'.join(env['LIBS']),
                                       ccflags = env['CCFLAGS'],
                                       loos_cxx = env['CXX'],
                                       loos_pythonpath = loos_pythonpath,
                                       ldlibrary = ':'.join(ldlibrary))

   outfile = open(str(target[0]), 'w')
   outfile.write(script)

   return None



# Verify that we have swig and it's v2.0+
# Returns the path to swig
def CheckForSwig(conf, min_version):
    conf.Message('Checking for Swig ...')
    # Need to use has_key() for older distros...
    if conf.env.has_key('SWIGVERSION'):
        if LooseVersion(conf.env['SWIGVERSION']) >= LooseVersion(min_version):
            conf.Result('yes')
            return(1)
        else:
            conf.Result('too old [%s, requires at least %s; pyloos disabled]' % (conf.env['SWIGVERSION'], min_version))
            return(0)

    conf.Result('no [pyloos disabled]')
    return(0)


# See if a library requires another to link...
def CheckAtlasRequires(conf, name, lib, required):

    conf.Message('Checking if %s requires %s ... ' % (name, required))
    lastLIBS = conf.env['LIBS']
    conf.env.Append(LIBS=lib)

#    test_code = """
#extern "C"{void dgesvd_(char*, char*, int*, int*, double*, int*, double*, double*, int*, double*, int*#, double*, int*, int*);}
#int main(int argc, char *argv[]) { char C[1]; double D[1];int I[1];dgesvd_(C, C, I, I, D, I, D, D, I, #D, I, D, I, I); }
#"""
    test_code="int main(){return(0);}"

    result = conf.TryLink(test_code, '.cpp')
    if not result:
        conf.env.Append(LIBS=required)
        result = conf.TryLink(test_code, '.cpp')
        conf.env.Replace(LIBS=lastLIBS)
        if not result:
            conf.Result('fail')
            return()
        conf.Result('yes')
        return(lib, required)

    conf.env.Replace(LIBS=lastLIBS)
    conf.Result('no')
    return(lib)

    

# Check for existince of boost library with various naming variants
# Will return a tuple containing the correct name and a flag indicating
# whether this is the threaded or non-threaded version.
# This will only search specified paths, not the built-in paths for g++,
# so some libraries may be missed...
def CheckForBoostLibrary(conf, name, path, suffix):
   conf.Message('Checking for Boost library %s...' % name)
   name = 'boost_' + name

   def sortByLength(w1,w2):
      return len(w1)-len(w2)

    # Now check for names lib libboost_regex-gcc43-mt.so ...
   files = glob.glob(os.path.join(path, 'lib%s*-mt.%s' % (name, suffix)))
   files.sort(cmp=sortByLength)
   if files:
      conf.Result(name + '-mt')
      name = os.path.basename(files[0])[3:-(len(suffix)+1)]
      return(name, 1)

   files = glob.glob(os.path.join(path, 'lib%s*.%s' % (name, suffix)))
   files.sort(cmp=sortByLength)
   if files:
      conf.Result(name)
      name = os.path.basename(files[0])[3:-(len(suffix)+1)]
      return(name, 0)


   conf.Result('missing')
   return('', -1)


# Check for Boost include files...
def CheckBoostHeaders(conf):
    test_code = """
#include <boost/version.hpp>
int main(int argc, char *argv[]) { return(0); }
"""

    conf.Message('Checking for Boost... ')
    result = conf.TryLink(test_code, '.cpp')
    if not result:
        conf.Result('no')
        return(0)

    conf.Result('yes')
    return(1)

            
# Check for version of Boost includes
def CheckBoostHeaderVersion(conf, min_boost_version):
    source_code = """
#include <iostream>
#include <boost/version.hpp>
int main(int argc, char *argv[]) { std::cout << BOOST_LIB_VERSION; return(0); }
"""

    conf.Message('Checking Boost version... ')
    result = conf.TryRun(source_code, '.cpp')
    if not result[0]:
        conf.Result('boost missing or incomplete?')
        return(0)
    version = result[1]

    if LooseVersion(version) < LooseVersion(min_boost_version):
        conf.Result('%s [too old, LOOS requires at least %s]' % (version, min_boost_version))
        return(0)

    conf.Result('%s [ok]' % version)
    return(1)

# Check for presence of a directory
def CheckDirectory(conf, dirname):

    conf.Message('Checking for directory %s...' % dirname)
    if os.path.isdir(dirname):
        conf.Result('yes')
        return(1)
    conf.Result('no')
    return(0)


def SetupBoostPaths(env):

    BOOST=env['BOOST']
    BOOST_INCLUDE=env['BOOST_INCLUDE']
    BOOST_LIBPATH=env['BOOST_LIBPATH']
    BOOST_LIBS = env['BOOST_LIBS']

    boost_libpath = ''
    boost_include = ''

    if BOOST:
        boost = BOOST
        boost_include = boost + '/include'
        boost_libpath = boost + '/lib'
        loos_build_config.user_libdirs['BOOST'] = boost_libpath
        loos_build_config.user_boost_flag = 1
        
    if BOOST_INCLUDE:
        boost_include = BOOST_INCLUDE
    if BOOST_LIBPATH:
        boost_libpath= BOOST_LIBPATH
        loos_build_config.user_libdirs['BOOST'] = boost_libpath
        loos_build_config.user_boost_flag = 1
       
    if boost_libpath:
        env.Prepend(LIBPATH=[boost_libpath])
        env['BOOST_LIBPATH'] = boost_libpath
    if boost_include:
        env.Prepend(CPPPATH=[boost_include] )




def SetupNetCDFPaths(env):
    NETCDF=env['NETCDF']
    NETCDF_INCLUDE=env['NETCDF_INCLUDE']
    NETCDF_LIBPATH=env['NETCDF_LIBPATH']
    NETCDF_LIBS = env['NETCDF_LIBS']
    
    netcdf_libpath = ''
    netcdf_include = ''

    if NETCDF:
        netcdf = NETCDF
        netcdf_include = netcdf + '/include'
        netcdf_libpath = netcdf + '/lib'
        loos_build_config.user_libdirs['NETCDF'] = netcdf_libpath

    if NETCDF_INCLUDE:
        netcdf_include = NETCDF_INCLUDE
    if NETCDF_LIBPATH:
        netcdf_libpath= NETCDF_LIBPATH
        loos_build_config.user_libdirs['NETCDF'] = netcdf_libpath

    if netcdf_libpath:
        env.Prepend(LIBPATH=[netcdf_libpath])
    if netcdf_include:
        env.Prepend(CPPPATH=[netcdf_include])



def AutoConfigSystemBoost(conf):
    boost_libs = []
    first = 1
    thread_suffix = 0

    for libname in loos_build_config.required_boost_libraries:
        if first:
            first = 0
            full_libname = 'boost_' + libname + '-mt'
            result = conf.CheckLib(full_libname, autoadd = 0)
            if result:
                boost_libs.append(full_libname)
                thread_suffix = 1
            else:
                full_libname = 'boost_' + libname
                result = conf.CheckLib(full_libname, autoadd = 0)
                if result:
                    boost_libs.append(full_libname)
        else:
            full_libname = 'boost_' + libname
            if thread_suffix:
                full_libname += '-mt'
            result = conf.CheckLib(full_libname, autoadd = 0)
            if result:
                boost_libs.append(full_libname)
            else:
                print 'Error- missing Boost library %s' % libname
                conf.env.Exit(1)


    return boost_libs



def AutoConfigUserBoost(conf):
    boost_libs = []
    first = 1
    thread_suffix = 0

    for libname in loos_build_config.required_boost_libraries:
        result = conf.CheckForBoostLibrary(libname, conf.env['BOOST_LIBPATH'], loos_build_config.suffix)
        if not result[0]:
            print 'Error- missing Boost library %s' % libname
            conf.env.Exit(1)
        if first:
            thread_suffix = result[1]
        else:
            if thread_suffix and not result[1]:
                print 'Error- expected %s-mt but found %s' % (libname, libname)
                conf.env.Exit(1)
            elif not thread_suffix and result[1]:
                print 'Error- expected %s but found %s-mt' % (libname, libname)
                conf.env.Exit(1)
        boost_libs.append(result[0])

    return boost_libs







def AutoConfiguration(env):
    conf = env.Configure(custom_tests = { 'CheckForSwig' : CheckForSwig,
                                          'CheckBoostHeaders' : CheckBoostHeaders,
                                          'CheckForBoostLibrary' : CheckForBoostLibrary,
                                          'CheckBoostHeaderVersion' : CheckBoostHeaderVersion,
                                          'CheckDirectory' : CheckDirectory,
                                          'CheckAtlasRequires' : CheckAtlasRequires,
                                          'CheckSystemType' : CheckSystemType
                                          })
    

    # Get system information
    conf.CheckSystemType()

    conf.env['host_type'] = loos_build_config.host_type
    conf.env['linux_type'] = loos_build_config.linux_type

    
    if env.GetOption('clean') or env.GetOption('help'):
        env['HAS_NETCDF'] = 1
    else:
        has_netcdf = 0
        
    
        # Some distros use /usr/lib, others have /usr/lib64.
        # Check to see what's here and prefer lib64 to lib
        if not conf.CheckDirectory('/usr/lib64'):
            if not conf.CheckDirectory('/usr/lib'):
                print 'Fatal error- cannot find your system library directory'
                conf.env.Exit(1)
            default_lib_path = '/usr/lib'
        else:
            # /usr/lib64 is found, so make sure we link against this (and not against any 32-bit libs)
            default_lib_path = '/usr/lib64'
            conf.env.Append(LIBPATH = '/usr/lib64')
       
        # Only setup ATLAS if we're not on a Mac...
        if loos_build_config.host_type != 'Darwin':
            ATLAS_LIBPATH = env['ATLAS_LIBPATH']
            ATLAS_LIBS = env['ATLAS_LIBS']
            if not ATLAS_LIBPATH:
                atlas_libpath = default_lib_path + '/atlas'
            else:
                atlas_libpath = ATLAS_LIBPATH
                loos_build_config.user_libdirs['ATLAS'] = atlas_libpath

            conf.env.Prepend(LIBPATH = [atlas_libpath])

        # Now that we know the default library path, setup Boost, NetCDF, and ATLAS
        # based on the environment or custom.py file
        SetupBoostPaths(conf.env)
        SetupNetCDFPaths(conf.env)



        # Check for standard typedefs...
        if not conf.CheckType('ulong','#include <sys/types.h>\n'):
            conf.env.Append(CCFLAGS = '-DREQUIRES_ULONG')
        if not conf.CheckType('uint','#include <sys/types.h>\n'):
            conf.env.Append(CCFLAGS = '-DREQUIRES_UINT')


        # --- NetCDF Autoconf
        has_netcdf = 0
        if conf.env['NETCDF_LIBS']:
            netcdf_libs = env['NETCDF_LIBS']
            conf.env.Append(CCFLAGS=['-DHAS_NETCDF'])
            has_netcdf = 1
        else:
            if conf.CheckLibWithHeader('netcdf', 'netcdf.h', 'c'):    # Should we check C or C++?
                netcdf_libs = 'netcdf'
                conf.env.Append(CCFLAGS=['-DHAS_NETCDF'])
                has_netcdf = 1

        conf.env['HAS_NETCDF'] = has_netcdf


        # --- Swig Autoconf (unless user requested NO PyLOOS)
        if int(env['pyloos']):
            if conf.CheckForSwig(loos_build_config.min_swig_version):
                conf.env['pyloos'] = 1
            else:
                conf.env['pyloos'] = 0

        # --- Boost Autoconf
        if not conf.CheckBoostHeaders():
            conf.env.Exit(1)

        if not conf.CheckBoostHeaderVersion(loos_build_config.min_boost_version):
            conf.env.Exit(1)

        if conf.env['BOOST_LIBS']:
            boost_libs = Split(env['BOOST_LIBS'])
        else:
            if not loos_build_config.user_boost_flag:
                boost_libs = AutoConfigSystemBoost(conf)
            else:
                boost_libs = AutoConfigUserBoost(conf)

            env.Append(LIBS = boost_libs)


        # --- Check for ATLAS/LAPACK and how to build

        # MacOS will use accelerate framework, so skip all of this...
        if loos_build_config.host_type != 'Darwin':
            if env['ATLAS_LIBS']:
                atlas_libs = env.Split(env['ATLAS_LIBS'])
            else:
                numerics = { 'atlas' : 0,
                             'lapack' : 0,
                             'f77blas' : 0,
                             'cblas' : 0,
                             'blas' : 0 }
                
        
                for libname in numerics.keys():
                    if conf.CheckLib(libname, autoadd = 0):
                        numerics[libname] = 1

                atlas_libs = []
                if (numerics['lapack']):
                    atlas_libs.append('lapack')
            
                if (numerics['f77blas'] and numerics['cblas']):
                    atlas_libs.extend(['f77blas', 'cblas'])
                elif (numerics['blas']):
                    atlas_libs.append('blas')
                else:
                    print 'Error- you must have some kind of blas installed'
                    conf.env.Exit(1)
                    
                if (numerics['atlas']):
                    atlas_libs.append('atlas')

                if not (numerics['lapack'] or numerics['atlas']):
                    # Did we miss atlas above because it requires gfortran?
                    if not numerics['atlas'] and (numerics['f77blas'] and numerics['cblas']):
                        atlas_libs = conf.CheckAtlasRequires('atlas', 'atlas' + atlas_libs, 'gfortran')
                        if not atlas_libs:
                            print 'Error- could not figure out how to build with Atlas/lapack'

                    # In some cases, lapack requires blas to link so the above
                    # check will find blas but not lapack
                    elif numerics['blas']:
                        result = conf.CheckAtlasRequires('lapack', 'lapack', 'blas')
                        if result:
                            atlas_libs.append('lapack')
                        else:
                            print 'Error- you must have either Lapack or Atlas installed'
                            conf.env.Exit(1)
                    else:
                        print 'Error- you must have either Lapack or Atlas installed'
                        conf.env.Exit(1)

                if not atlas_libs:
                    print 'Error- could not figure out how to build with Atlas/Lapack'
                    conf.env.Exit(1)

                # Hack to extend list rather than append a list into a list
            for lib in atlas_libs:
                env.Append(LIBS=lib)

        environOverride(conf)
        env = conf.Finish()


#########################################################################################3

def addDeprecatedOptions(opt):
    from SCons.Variables import PathVariable

    opt.Add(PathVariable('LAPACK', 'Path to LAPACK', '', PathVariable.PathAccept))
    opt.Add(PathVariable('ATLAS', 'Path to ATLAS', '', PathVariable.PathAccept))
    opt.Add(PathVariable('ATLASINC', 'Path to ATLAS includes', '', PathVariable.PathAccept))
    opt.Add(PathVariable('BOOSTLIB', 'Path to BOOST libraries', '', PathVariable.PathAccept))
    opt.Add(PathVariable('BOOSTINC', 'Path to BOOST includes', '', PathVariable.PathAccept))
    opt.Add('BOOSTREGEX', 'Boost regex library name', '')
    opt.Add('BOOSTPO', 'Boost program options library name', '')
    opt.Add(PathVariable('LIBXTRA', 'Path to additional libraries', '', PathVariable.PathAccept))
    opt.Add(PathVariable('NETCDFINC', 'Path to netcdf include files', '', PathVariable.PathAccept))
    opt.Add(PathVariable('NETCDFLIB', 'Path to netcdf library files', '', PathVariable.PathAccept))
    opt.Add(PathVariable('ALTPATH', 'Additional path to commands', '', PathVariable.PathAccept))
    opt.Add(PathVariable('LIBS_OVERRIDE', 'Override linked libs', '', PathVariable.PathAccept))
    opt.Add(PathVariable('LIBS_PATHS_OVERRIDE', 'Override paths to libs', '', PathVariable.PathAccept))

def makeDeprecatedVariableWarning():
    state = { 'warned' : 0 }

    def warning(what, mapto):
        if not state['warned']:
            state['warned'] = 1
            print """
***WARNING***
You are using old-style (deprecated) variables either
on the command line or in your custom.py file.  These
will be ignored.  The following deprecated variables
are set,
"""
        print '\t%s: %s' % (what, mapto)
    return warning


def checkForDeprecatedOptions(env):
    mapping = {
        'LAPACK' : 'use ATLAS_LIBPATH',
        'ATLAS' : 'use ATLAS_LIBPATH',
        'ATLASINC' : 'no replacement',
        'BOOSTLIB' : 'use BOOST_LIBPATH or BOOST',
        'BOOSTINC' : 'use BOOST_INCLUDE or BOOST',
        'BOOSTREGEX' : 'use BOOST_LIBS',
        'BOOSTPO' : 'use BOOST_LIBS',
        'LIBXTRA' : 'use ATLAS_LIBS, BOOST_LIBS, or NETCDF_LIBS',
        'NETCDFINC' : 'use NETCDF_INCLUDE or NETCDF',
        'NETCDFLIB' : 'use NETCDF_LIBPATH or NETCDF',
        'ALTPATH' : 'Set your shell PATH instead',
        'LIBS_OVERRIDE' : 'use ATLAS_LIBS, BOOST_LIBS, or NETCDF_LIBS',
        'LIBS_PATHS_OVERRIDE' : 'use ATLAS_LIBPATH, BOOST_LIBPATH, or NETCDF_LIBPATH'
        }
    
    warner = makeDeprecatedVariableWarning()
    for name in mapping:
        if env.has_key(name):
            if env[name]:
                warner(name, mapping[name])