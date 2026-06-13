from discordrpc import Activity, StatusDisplay
from dataclasses import dataclass, field

# discord-rpc docs: https://senophyx.id/docs/discord-rpc/
# discord docs: https://docs.discord.com/developers/discord-social-sdk/development-guides/setting-rich-presence#understanding-rich-presence

@dataclass
class Presence:
    name: str # displayed as the first line on member list
    type: str # accepts only 'PLAYING', 'WATCHING', or 'LISTENING'
    details: str # displayed when you click on the status
    timeSent: float

    activityType: Activity = field(init = False)
    statusDisplayType: StatusDisplay = field(init = False, default = StatusDisplay.State)

    def __post_init__(self):
        if self.type not in ['PLAYING', 'WATCHING', 'LISTENING']: raise ValueError(f'Invalid activity type: {self.type}')
        
        if self.type == 'PLAYING': self.activityType = Activity.Playing
        elif self.type == 'WATCHING': self.activityType = Activity.Watching
        elif self.type == 'LISTENING': self.activityType = Activity.Listening

@dataclass(kw_only = True)
class VideoPresence(Presence):
    state_url: str
    activityType: Activity = field(init = False)
    thumbnail: str = None
    currentTime: int
    duration: int

    def __post_init__(self):
        self.activityType = Activity.Watching

@dataclass
class MusicPresence(VideoPresence):
    activityType: Activity = field(init = False) 

    def __post_init__(self):
        self.activityType = Activity.Listening