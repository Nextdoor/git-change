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
        A list of strings representing the absolute paths to directories of
        files changed in the last commit.
    """
    # Get a list of changed files in the HEAD commit.
    changed_files = git.run_command(
        'git diff --name-only HEAD^ HEAD', trap_stdout=True).split('\n')[:-1]

    # Return absolute paths to the parent dirs of changed files.
    repo_root = _get_repo_root()
    dir_paths = [os.path.dirname(os.path.join(repo_root, path)) for path in changed_files]
    return list(set(dir_paths))


def get_owners_for_dir(dir_path):
    """Gets the owners of a directory by recursively looking in OWNERS files.

    If a directory does not contain an OWNERS file, the owners of the directory
    are the owners of the directory's parent.

    Args:
        dir_path: A string representing the absolute path to a directory.

    Returns:
        A list of strings representing Gerrit usernames.
    """
    # If we have recursed past the top of the repo, there are no owners.
    if dir_path == os.path.dirname(_get_repo_root()):
        return []

    # If this directory exists, attempt to find it's explicit owners.
    if os.path.exists(dir_path):
        for file in os.listdir(dir_path):
            file_path = os.path.join(dir_path, file)
            if _is_owners_file(file_path):
                return [line.strip() for line in open(file_path, 'r')]

    # Otherwise, recurse up the tree to find the owners for this directory.
    return get_owners_for_dir(os.path.dirname(dir_path))


def _is_owners_file(path):
    """Checks if the given path is a path to a OWNERS file."""
    return os.path.isfile(path) and os.path.basename(path) == OWNERS_FILE


def _get_repo_root():
    """Returns the absolute path to the root of the git repo."""
    return git.run_command('git rev-parse --show-toplevel', trap_stdout=True).strip()
