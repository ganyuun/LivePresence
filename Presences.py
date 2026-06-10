from pypresence.types import ActivityType, StatusDisplayType
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# pypresence docs: https://qwertyquerty.github.io/pypresence/html/doc/presence.html
# discord docs: https://docs.discord.com/developers/discord-social-sdk/development-guides/setting-rich-presence#understanding-rich-presence

@dataclass
class Activity:
    name: str # displayed as the first line on member list
    type: str # accepts only 'PLAYING', 'WATCHING', or 'LISTENING'
    details: str # displayed when you click on the status
    priority: int # determined by order of presences in GUI

    activityType: ActivityType = field(init = False)
    displayType: StatusDisplayType = field(init = False, default = StatusDisplayType.STATE)

    def __post_init__(self):
        if self.type not in ['PLAYING', 'WATCHING', 'LISTENING']: raise ValueError(f'Invalid activity type: {self.type}')
        
        if self.type == 'PLAYING': self.activityType = ActivityType.PLAYING
        elif self.type == 'WATCHING': self.activityType = ActivityType.WATCHING
        elif self.type == 'LISTENING': self.activityType = ActivityType.LISTENING

@dataclass(kw_only = True)
class VideoActivity(Activity):
    def calcEnd(self, hours: int, minutes: int, seconds: int):
        result = self.start + timedelta(hours = hours, minutes = minutes, seconds = seconds)
        return int(result.timestamp())

    state_url: str
    activityType: ActivityType = ActivityType.WATCHING
    start: int = int(datetime.now().timestamp())
    end: int = field(default_factory = calcEnd)

@dataclass
class MusicActivity(VideoActivity):
    activityType: ActivityType = ActivityType.LISTENING