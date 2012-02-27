#!/usr/bin/python2.6

"""Git subcommand which creates a Gerrit change.

Creates a change for the Gerrit code review tool. The files the make
up the change must be staged for commit, and are committed in a new
branch meant to exist exclusively for this change.

Performs the following operations:
  1. Notes the current tracking branch
  2. Creates a temporary, local change branch
  3. Commits staged changes
  4. Pushes to the previously current branch
  5. Renames the branch to reflect the Gerrit Change-Id

If there are commits in the tracking branch not yet merged in the
remote branch prior to step 3 above, a warning is issued to explain
that continuing would result in multiple changes being added to the
temporary branch and pushed to Gerrit.
"""

__author__ = 'jacob@nextdoor.com (Jacob Hesch)'

import sys
import time

import gflags

import git

gflags.DEFINE_list('reviewers', list(), 'comma separated list of reviewers', short_name='r')
gflags.DEFINE_list('cc', list(), 'comma separated list of people to cc')
gflags.DEFINE_string('bug', None, 'bug number', short_name='b')
gflags.DEFINE_string('message', None, 'commit message', short_name='m')
gflags.DEFINE_string('topic', None, 'topic')

gflags.DEFINE_string('remote', 'origin', 'name of the git remote repository')
gflags.DEFINE_bool('fetch', False, 'whether to run git fetch so that remote branch is in sync')

FLAGS = gflags.FLAGS


def get_change_id_from_head():
    """Returns the change ID of the last commit.

    If the change ID is available as the value of the Change-Id
    attribute in the HEAD commit message, that value is returned. If
    there is no Change-Id attribute, returns None.

    Returns:
        A string representing the HEAD commit's change ID if it is
        available or None if not.
    """
    output = git.run_command('git cat-file -p HEAD')
    lines = output.split('\n')
    for line in lines:
        if line.startswith('Change-Id:'):
            _, change_id = line.split(':')
            return change_id.strip()
    return None


def check_unmerged_commits(branch):
    """Checks whether the given branch has unmerged commits.

    Args:
        branch: A strings representing a local tracking branch.

    Returns:
        True if the given local tracking branch has commits not yet
        merged in its remote branch. False if not, or if the user
        elected to proceed anyway.
    """
    output = git.run_command('git log --oneline %s ^origin/%s' % (branch, branch))
    if not output or FLAGS.dry_run:
        return False

    print 'Your branch %s is ahead of its remote by the following %s commit(s):\n' % (
        branch, len(output.split('\n')))
    print output
    user_input = raw_input(
        '\nIf we continue, multiple commits will be added to the new branch and\n'
        'pushed for review. Those commits will have submit dependencies in Gerrit.\n'
        'You might try syncing the remote branch by passing the --fetch flag.\n'
        'Continue? ')
    if user_input.lower().startswith('y'):
        return False

    print '\nAborted'
    return True


def commit_change():
    """Commits the staged change.

    Runs git commit to commit the staged change. If a bug number was
    specified in a flag, sets the ND_BUG_ID environment variable so
    the prepare-commit-msg hook can inject the bug ID into the commit
    message.
    """
    if FLAGS.bug is None:
        env = None
    else:
        env = {'ND_BUG_ID': FLAGS.bug}
    command = 'git commit'
    if FLAGS.message is not None:
        command = '%s -m %s' % (command, FLAGS.message)
    git.run_command_shell(command, env=env)


def build_push_command(branch):
    """Builds a git push command string for pushing a Gerrit change.

    The command is built using the given branch and flag values to
    populate remote repository, reviewers, users to CC, etc.

    Args:
        branch: A string representing the branch to which to push.

    Returns:
        The git push command as a string.
    """
    command = 'git push %s' % FLAGS.remote
    receive_pack_args = []
    for reviewer in FLAGS.reviewers:
        receive_pack_args.append('--reviewer=%s' % reviewer)
    for cc in FLAGS.cc:
        receive_pack_args.append('--cc=%s' % cc)
    if receive_pack_args:
        command = '%s --receive-pack="git receive-pack %s"' % (
            command, ' '.join(receive_pack_args))
    command = '%s HEAD:refs/for/%s' % (command, branch)
    if FLAGS.topic:
        command = '%s/%s' % (command, FLAGS.topic)
    return command


def main(argv):
    if not git.run_command('git diff --cached --name-status'):
        print 'You have no staged changes; exiting'
        sys.exit(1)

    original_branch = git.get_branch()

    # Fetch from origin so that we can see how many commits ahead our
    # local branch is.
    if FLAGS.fetch:
        output = git.run_command('git fetch origin')
        if output:
            print output

    if check_unmerged_commits(original_branch):
        sys.exit(1)

    # Create a temporary branch until we have a change ID.
    tmp_branch = 'tmp-change-%s' % time.time()
    git.run_command('git checkout -b %s' % tmp_branch)

    # Commit the change. A change ID will be generated as a
    # side-effect.
    commit_change()

    # Now rename the branch according to the change ID.
    change_id = get_change_id_from_head()
    if change_id is None:
        # We couldn't read a change ID for some reason so just keep
        # the temp name.
        new_branch = tmp_branch
    else:
        new_branch = 'change-%s' % change_id
        git.run_command('git branch -m %s %s' % (tmp_branch, new_branch))
    print 'Created branch %s' % new_branch

    output = git.run_command(build_push_command(original_branch))
    print output

    git.run_command('git checkout %s' % original_branch)


if __name__ == '__main__':
    git.app(sys.argv)
