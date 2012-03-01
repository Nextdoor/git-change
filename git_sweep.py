#!/usr/bin/env python

"""Git subcommand to remove temporary change branches.

Temporary change branches are created by git-change and are name like
change-Id06774ede265426f85d36cca50bba69d8aa54ed8 (where I... is a
Gerrit change ID). See git_change.py.
"""

__author__ = 'jacob@nextdoor.com (Jacob Hesch)'

import sys

import gflags

import git

gflags.DEFINE_bool('pull', False, 'Run git-pull prior to sweeping change branches.')

FLAGS = gflags.FLAGS


def get_temp_branches():
    """Returns temporary change branches.

    Temporary change branch names match the pattern 'change-*'.

    Returns:
        A sequence of strings each representing a branch names.
    """
    output = git.run_command(
        'git for-each-ref --format="%(refname:short)" refs/heads/change-*')
    if output:
        return output.split('\n')
    else:
        return []


def main(argv):
    if FLAGS.pull:
        output = git.run_command('git pull %s' % FLAGS.remote)
        if output:
            print output

    unmerged_branches = []
    for branch in get_temp_branches():
        try:
            git.run_command('git branch -d %s' % branch, output_on_error=False)
        except git.CalledProcessError, e:
            unmerged_branches.append(branch)
        else:
            print '\nDeleted branch %s\n' % branch

    if unmerged_branches:
        print ('The following change branches could not be deleted, probably because they\n'
               'are not fully merged into the current branch. You might try again with\n'
               'the --pull flag in order to sync with remote.\n')
        for branch in unmerged_branches:
            print branch


if __name__ == '__main__':
    git.app(sys.argv)
