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
            maybe_rm('sdist')


setup(
    name='git-change',
    version=__import__(PACKAGE).__version__,
    description='git command to create and manage Gerrit changes',
    long_description=open('README.rst').read(),
    author='Jacob Hesch',
    author_email='jacob+git-change@nextdoor.com',
    url='https://github.com/Nextdoor/git-change',
    keywords='gerrit git code review',
    packages=[PACKAGE],
    entry_points={
        'console_scripts': ['git-change = git_change.git_change:app'],
    },
    data_files=[
        ('man/man1', ['git-change.1']),
    ],
    install_requires=[
        'python-gflags',
        'setuptools',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Topic :: Software Development',
        'Intended Audience :: Developers',
        'Programming Language :: Python',
        'Operating System :: POSIX',
        'Natural Language :: English',
    ],
    cmdclass={'sdist': SourceDistHook, 'clean': CleanHook},
)
