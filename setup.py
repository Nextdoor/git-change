# Copyright 2012 Nextdoor.com, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import shutil
import subprocess

from distutils.command.clean import clean
from distutils.command.sdist import sdist
from setuptools import setup

PACKAGE = 'git_change'


class SourceDistHook(sdist):

    def run(self):
        subprocess.call(['rst2man', 'git-change.rst', 'git-change.1'])
        sdist.run(self)
        os.unlink('git-change.1')
        os.unlink('MANIFEST')


class CleanHook(clean):

    def run(self):
        clean.run(self)

        def maybe_rm(path):
            if os.path.exists(path):
                shutil.rmtree(path)
        if self.all:
            maybe_rm('git_change.egg-info')
            maybe_rm('dist')


setup(
    name='git-change',
    version=__import__(PACKAGE).__version__,
    description='Git command to create and manage Gerrit changes',
    long_description=open('README.rst').read(),
    author='Jacob Hesch',
    author_email='jacob@nextdoor.com',
    url='https://github.com/Nextdoor/git-change',
    license='Apache License, Version 2.0',
    keywords='gerrit git code review',
    packages=[PACKAGE],
    entry_points={
        'console_scripts': ['git-change = git_change.git_change:app'],
    },
    data_files=[
        ('man/man1', ['git-change.1']),
        ('etc/bash_completion.d', ['extras/bash_completion.d/git-change']),
    ],
    install_requires=[
        'python-gflags',
        'setuptools',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Topic :: Software Development',
        'License :: OSI Approved :: Apache Software License',
        'Intended Audience :: Developers',
        'Programming Language :: Python',
        'Operating System :: POSIX',
        'Natural Language :: English',
    ],
    cmdclass={'sdist': SourceDistHook, 'clean': CleanHook},
)
