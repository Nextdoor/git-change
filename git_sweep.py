#!/usr/bin/python2.6

"""Git subcommand to remove temporary change branches.

Temporary change branches are created by git-change and are name like
change-Id06774ede265426f85d36cca50bba69d8aa54ed8 (where I... is a
Gerrit change ID). See git_change.py.
"""

__author__ = 'jacob@nextdoor.com (Jacob Hesch)'

import sys

import gflags

import git

gflags.DEFINE_bool('pull', False, 'whether to run git pull')

FLAGS = gflags.FLAGS


def get_temp_branches():
    """Returns temporary change branches.

    Temporary change branch names match the pattern 'change-*'.

    Returns:
        A sequence of strings each representing a branch names.
    """
    return git.run_command(
        'git for-each-ref --format="%(refname:short)" refs/heads/change-*').split('\n')


def main(argv):
    if FLAGS.pull:
        output = git.run_command('git pull %s' % FLAGS.remote)
        if output:
            print output

    errors = False
    for branch in get_temp_branches():
        try:
            git.run_command('git branch -d %s' % branch, output_on_error=False)
        except git.CalledProcessError, e:
            print e.output
            errors = True
        else:
            print '\nDeleted branch %s\n' % branch

    if errors:
        print ('Some branches could not be deleted, probably '
               'because they are not fully merged.\n'
               'You might try passing --pull to sync.')


if __name__ == '__main__':
    git.app(sys.argv)
