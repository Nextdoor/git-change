# Copyright 2014 Nextdoor.com, Inc.
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


"""A module to handling the semantics of OWNERS files.

This module introduces the concept of an OWNERS file: a plaintext file in your
codebase containing Gerrit usernames specifying the "owners" of a directory and
its sub-directories recursively. (Note that a OWNERS file is overridden by an
OWNERS file in a sub-directory for that sub-directory.) Owners will then be
added to code reviews for code they own automatically.

To use OWNERS files, first configure your repository:
    $ git config git-change.include-owners true

Then any file you add named "OWNERS" will be interpreted as an owners file by
this module with the semantics described above. Be sure to only include Gerrit
usernames in owners files, with newlines between each one.

    $ cat OWNERS
    a-gerrit-username
    another-gerrit-username
"""

__author__ = 'mcqueen@nextdoor.com (Sean McQueen)'

import os

import git

OWNERS_FILE = 'OWNERS'

def get_change_owners():
    """Gets owners of changed files from OWNERS files.

    Returns:
        A list of strings representing Gerrit usernames with no duplicates.
    """
    owners = set()
    for directory in get_directories_with_changes():
        owners.update(get_owners_for_dir(directory))
    return list(owners)


def get_directories_with_changes():
    """Gets the absolute paths to the parent directories of changed files.

    Returns:
        A list of strings representing the absolute paths to directories with
        changed files in the last commit, with no duplicates.
    """
    # Get a list of changed files in the HEAD commit.
    head_commit = git.run_command('git rev-parse HEAD', trap_stdout=True).strip()
    changed_files_cmd = 'git diff-tree --no-commit-id --name-only -r %s' % head_commit
    changed_files = git.run_command(changed_files_cmd, trap_stdout=True).split('\n')[:-1]

    # Return the absolute paths to their parent directories, removing duplicates.
    abs_dir_paths = [os.path.dirname(os.path.abspath(path)) for path in changed_files]
    return list(set(abs_dir_paths))


def get_owners_for_dir(dir_path):
    """Gets the owners of a directory by recursively looking in OWNERS files.

    If a directory does not contain an OWNERS file, the owners of the directory
    are the owners of the directory's parent.

    Args:
        dir_path: A string representing the absolute path to a directory.

    Returns:
        A list of strings, representing Gerrit usernames, with no duplicate
        strings.
    """
    # Return the explicit owners of this directory if they exist.
    for file in os.listdir(dir_path):
        file_path = os.path.join(dir_path, file)
        if _is_owners_file(file_path):
            return [line.strip() for line in open(file_path, 'r')]

    # Otherwise recurse up the file tree to find this directory's owners.
    if dir_path == _get_repo_root():
        return []
    else:
        return get_owners_for_dir(os.path.dirname(dir_path))


def _is_owners_file(path):
    """Checks if the given path is a path to a OWNERS file."""
    return os.path.isfile(path) and os.path.basename(path) == OWNERS_FILE


def _get_repo_root():
    """Returns the absolute path to the root of the git repo."""
    return git.run_command('git rev-parse --show-toplevel', trap_stdout=True).strip()
