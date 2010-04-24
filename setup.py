#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Tue Feb  9 18:42:57 CET 2010

"""Python distutils setup.py build script for Syncless.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import glob
import os
import os.path
import sys
import stat
from distutils import log
from distutils.core import Extension
from distutils.core import setup
from distutils.dist import Distribution
from distutils.command.build import build

class MyBuild(build):
  def has_sources(self):
    return self.has_pure_modules or self.has_ext_modules

  sub_commands = build.sub_commands + [
      ('build_ext_symlinks', build.has_ext_modules),
      ('build_src_symlinks', has_sources)]

class MyBuildExtSymlinks(build):
  """Create symlinks to .so files.
  
  Create symlinks so scripts in the source dir can be run with PYTHONPATH=.
  without install.
  """

  def run(self):
    log.info('build_ext_symlinks')
    # '.so'
    build_ext_cmd = self.get_finalized_command('build_ext')
    so_ext = build_ext_cmd.compiler.shared_lib_extension
    for ext in self.distribution.ext_modules:
      name_items = ext.name.split('.')
      if len(name_items) == 2 and os.path.isdir(name_items[0]):
        # build_ext_cmd.build_lib: 'build/lib.linux-i686-2.6'
        # '.'.join(name_items) == 'syncless/coio'
        so_file = os.path.join(build_ext_cmd.build_lib,
                               name_items[0], name_items[1] + so_ext)
        link_from = os.path.join(name_items[0], name_items[1] + so_ext)
        link_to = os.path.join('..', so_file)
        symlink(link_to, link_from)

class MyBuildSrcSymlinks(build):
  """Create symlinks to package source directories.
  
  Create symlinks so, if combined with MyBuildExtSymlinks, scripts in the
  source dir can be run even without PYTHONPATH=. without install.
  """

  def run(self):
    log.info('build_src_symlinks')
    src_dirs = self.distribution.symlink_script_src_dirs
    if src_dirs:
      for package in self.distribution.packages:  # package = 'syncless'
        package = package.replace('/', '.')
        if '.' not in package:
          for src_dir in src_dirs:  # src_dir = 'test'
            link_from = os.path.join(src_dir, package)
            link_to = os.path.join('..', package)
            symlink(link_to, link_from)

# Make self.distribution.symlink_script_src_dirs visible.
Distribution.symlink_script_src_dirs = None

def symlink(link_to, link_from):
  log.info('symlinking %s -> %s' % (link_from, link_to))
  try:
    st = os.lstat(link_from)
    if stat.S_ISLNK(st.st_mode):
      os.remove(link_from)  # Remove old symlink.
  except OSError:
    pass
  os.symlink(link_to, link_from)

# TODO(pts): Run this autodetection only for build_ext (just like in
# pysqlite).
# TODO(pts): Parse command-line flags (like include etc.)
# We could add more directories (e.g. those in /etc/ld.so.conf), but that's
# system-specific, see http://stackoverflow.com/questions/2230467 .
include_dirs = []
library_dirs = []
event = None
for prefix in os.getenv('LD_LIBRARY_PATH', '').split(':') + [
              sys.prefix, '/usr']:
  if (prefix and
      os.path.isfile(prefix + '/include/event.h') and
      os.path.isfile(prefix + '/include/evdns.h') and
      glob.glob(prefix + '/lib/libevent.*')):
    print 'found libevent in', prefix
    include_dirs =['%s/include' % prefix]
    library_dirs =['%s/lib' % prefix]    
    break
if not include_dirs:
  print 'libevent not found, may be present anyway, going on'
event = Extension(name='syncless.coio',
                  sources=['coio_src/coio.c'],
                  depends=['coio_src/coio_c_helper.h'],
                  include_dirs=include_dirs,
                  library_dirs=library_dirs,
                  libraries=['event'])

# chdir to to the directory containing setup.py. Building extensions wouldn't
# work otherwise.
os.chdir(os.path.dirname(__file__))
if __file__[0] != '/':
    __file__ = os.path.basename(__file__)

version = {}
f = open(os.path.join('syncless', 'version.py'))
exec f in version
assert isinstance(version.get('VERSION'), str)

setup(name='syncless',
      version=version['VERSION'],
      description='Syncless: asynchronous client and server library using Stackless Python',
      author='Peter Szabo',
      author_email='pts@fazekas.hu',
      maintainer='Peter Szabo',
      maintainer_email='pts@fazekas.hu',
      url='http://code.google.com/p/syncless/',
      download_url='http://syncless.googlecode.com/files/syncless-%s.tar.gz' %
                   version['VERSION'],
      packages=['syncless'],
      long_description=
          "Syncless is an experimental, lightweight, non-blocking "
          "(asynchronous) client and server socket network communication "
          "library for Stackless Python 2.6. For high speed, Syncless uses "
          "libevent, and parts of Syncless' code is implemented in C (Pyrex). "
          "Thus Syncless can be faster than many other non-blocking Python "
          "communication libraries. Syncless contains an asynchronous DNS "
          "resolver (using evdns) and a HTTP server capable of serving WSGI "
          "applications. Syncless aims to be a coroutine-based alternative of "
          "event-driven networking engines (such as Twisted and FriendFeed's "
          "Tornado), and it's a competitor of gevent, pyevent, eventlet and "
          "Concurrence.",
      license="GPL v2",
      platforms=["Unix"],
      classifiers=[
          "Development Status :: 3 - Alpha",
          "Environment :: Console",
          "Environment :: No Input/Output (Daemon)",
          "Environment :: Other Environment",
          "Intended Audience :: Developers",
          "License :: OSI Approved :: GNU General Public License (GPL)",
          "Operating System :: POSIX :: Linux",
          "Operating System :: Unix",
          "Programming Language :: Python :: 2.6",
          "Topic :: Internet",
          "Topic :: Internet :: WWW/HTTP :: Dynamic Content :: CGI Tools/Libraries",
          "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
          "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
          "Topic :: Internet :: WWW/HTTP :: WSGI :: Server",
          "Topic :: Software Development :: Libraries :: Application Frameworks",
          "Topic :: Software Development :: Libraries :: Python Modules",
      ],
      requires=['stackless'],
      ext_modules = [ event ],
      cmdclass = {'build': MyBuild,
                  'build_ext_symlinks': MyBuildExtSymlinks,
                  'build_src_symlinks': MyBuildSrcSymlinks,
                 },
      symlink_script_src_dirs=['test', 'benchmark', 'coio_src', 'examples'],
     )
