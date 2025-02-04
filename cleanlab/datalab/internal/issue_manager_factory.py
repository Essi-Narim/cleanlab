# Copyright (C) 2017-2023  Cleanlab Inc.
# This file is part of cleanlab.
#
# cleanlab is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# cleanlab is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with cleanlab.  If not, see <https://www.gnu.org/licenses/>.
"""The factory module provides a factory class for constructing concrete issue managers
and a decorator for registering new issue managers.

This module provides the :py:meth:`register` decorator for users to register new subclasses of
:py:class:`IssueManager <cleanlab.datalab.internal.issue_manager.issue_manager.IssueManager>`
in the registry. Each IssueManager detects some particular type of issue in a dataset.


Note
----

The :class:`REGISTRY` variable is used by the factory class to keep track
of registered issue managers.
The factory class is used as an implementation detail by
:py:class:`Datalab <cleanlab.datalab.datalab.Datalab>`,
which provides a simplified API for constructing concrete issue managers.
:py:class:`Datalab <cleanlab.datalab.datalab.Datalab>` is intended to be used by users
and provides detailed documentation on how to use the API.

Warning
-------
Neither the :class:`REGISTRY` variable nor the factory class should be used directly by users.
"""
from __future__ import annotations

from typing import Dict, List, Type

from cleanlab.datalab.internal.issue_manager import (
    ClassImbalanceIssueManager,
    DataValuationIssueManager,
    IssueManager,
    LabelIssueManager,
    NearDuplicateIssueManager,
    NonIIDIssueManager,
    OutlierIssueManager,
)
from cleanlab.datalab.internal.issue_manager.regression import RegressionLabelIssueManager

REGISTRY: Dict[str, Dict[str, Type[IssueManager]]] = {
    "classification": {
        "outlier": OutlierIssueManager,
        "label": LabelIssueManager,
        "near_duplicate": NearDuplicateIssueManager,
        "non_iid": NonIIDIssueManager,
        "class_imbalance": ClassImbalanceIssueManager,
        "data_valuation": DataValuationIssueManager,
    },
    "regression": {
        "label": RegressionLabelIssueManager,
    },
}
"""Registry of issue managers that can be constructed from a string
and used in the Datalab class.

:meta hide-value:

Currently, the following issue managers are registered by default:

- ``"outlier"``: :py:class:`OutlierIssueManager <cleanlab.datalab.internal.issue_manager.outlier.OutlierIssueManager>`
- ``"near_duplicate"``: :py:class:`NearDuplicateIssueManager <cleanlab.datalab.internal.issue_manager.duplicate.NearDuplicateIssueManager>`
- ``"non_iid"``: :py:class:`NonIIDIssueManager <cleanlab.datalab.internal.issue_manager.noniid.NonIIDIssueManager>`

Warning
-------
This variable should not be used directly by users.
"""


# Construct concrete issue manager with a from_str method
class _IssueManagerFactory:
    """Factory class for constructing concrete issue managers."""

    @classmethod
    def from_str(cls, issue_type: str, task: str) -> Type[IssueManager]:
        """Constructs a concrete issue manager class from a string."""
        if isinstance(issue_type, list):
            raise ValueError(
                "issue_type must be a string, not a list. Try using from_list instead."
            )

        if task not in REGISTRY:
            raise ValueError(f"Invalid task type: {task}, must be in {list(REGISTRY.keys())}")
        if issue_type not in REGISTRY[task]:
            raise ValueError(f"Invalid issue type: {issue_type} for task {task}")

        return REGISTRY[task][issue_type]

    @classmethod
    def from_list(cls, issue_types: List[str], task: str) -> List[Type[IssueManager]]:
        """Constructs a list of concrete issue manager classes from a list of strings."""
        return [cls.from_str(issue_type, task) for issue_type in issue_types]


def register(cls: Type[IssueManager], task: str = "classification") -> Type[IssueManager]:
    """Registers the issue manager factory.

    Parameters
    ----------
    cls :
        A subclass of
        :py:class:`IssueManager <cleanlab.datalab.internal.issue_manager.issue_manager.IssueManager>`.

    task :
        Specific machine learning task like classification or regression.

    Returns
    -------
    cls :
        The same class that was passed in.

    Example
    -------

    When defining a new subclass of
    :py:class:`IssueManager <cleanlab.datalab.internal.issue_manager.issue_manager.IssueManager>`,
    you can register it like so:

    .. code-block:: python

        from cleanlab import IssueManager
        from cleanlab.datalab.internal.issue_manager_factory import register

        @register
        class MyIssueManager(IssueManager):
            issue_name: str = "my_issue"
            def find_issues(self, **kwargs):
                # Some logic to find issues
                pass

    or in a function call:

    .. code-block:: python

        from cleanlab import IssueManager
        from cleanlab.datalab.internal.issue_manager_factory import register

        class MyIssueManager(IssueManager):
            issue_name: str = "my_issue"
            def find_issues(self, **kwargs):
                # Some logic to find issues
                pass

        register(MyIssueManager, task="classification")
    """

    if not issubclass(cls, IssueManager):
        raise ValueError(f"Class {cls} must be a subclass of IssueManager")

    name: str = str(cls.issue_name)

    if task not in REGISTRY:
        raise ValueError(f"Invalid task type: {task}, must be in {list(REGISTRY.keys())}")

    if name in REGISTRY[task]:
        print(
            f"Warning: Overwriting existing issue manager {name} with {cls} for task {task}."
            "This may cause unexpected behavior."
        )

    REGISTRY[task][name] = cls
    return cls


def list_possible_issue_types(task: str) -> List[str]:
    """Returns a list of all registered issue types.

    Any issue type that is not in this list cannot be used in the :py:meth:`find_issues` method.

    See Also
    --------
    :py:class:`REGISTRY <cleanlab.datalab.internal.issue_manager_factory.REGISTRY>` : All available issue types and their corresponding issue managers can be found here.
    """
    return list(REGISTRY.get(task, []))


def list_default_issue_types(task: str) -> List[str]:
    """Returns a list of the issue types that are run by default
    when :py:meth:`find_issues` is called without specifying `issue_types`.

    See Also
    --------
    :py:class:`REGISTRY <cleanlab.datalab.internal.issue_manager_factory.REGISTRY>` : All available issue types and their corresponding issue managers can be found here.
    """
    if task == "regression":
        default_issue_types = ["label"]
    else:
        default_issue_types = [
            "label",
            "outlier",
            "near_duplicate",
            "non_iid",
        ]
    return default_issue_types
