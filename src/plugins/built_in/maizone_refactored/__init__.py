# -*- coding: utf-8 -*-
"""
让框架能够发现并加载子目录中的组件。
"""

from .plugin import MaiZoneRefactoredPlugin as MaiZoneRefactoredPlugin
from .actions.send_feed_action import SendFeedAction as SendFeedAction
from .actions.read_feed_action import ReadFeedAction as ReadFeedAction
from .commands.send_feed_command import SendFeedCommand as SendFeedCommand
