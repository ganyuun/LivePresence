import discordrpc, asyncio, json
from discordrpc import Activity, utils
from dataclasses import dataclass, field
from datetime import datetime

# discord-rpc docs: https://github.com/Senophyx/Discord-RPC/blob/main/DOCS.md
# discord docs: https://docs.discord.com/developers/discord-social-sdk/development-guides/setting-rich-presence#understanding-rich-presence

@dataclass
class Presence:
    name: str # displayed in sidebar
    type: str # accepts only 'PLAYING', 'STREAMING', 'WATCHING', or 'LISTENING'
    details: str # line 1 of activity
    timeSent: float
    state: str = None # line 2 of activity
    thumbnail: str = None

    activityType: Activity = field(init = False)

    def __post_init__(self):
        if self.type not in {'PLAYING', 'STREAMING', 'WATCHING', 'LISTENING'}: raise ValueError(f'Invalid activity type: {self.type}')
        
        match self.type:
            case 'PLAYING': self.activityType = Activity.Playing
            case 'STREAMING': self.activityType = Activity.Watching
            case 'WATCHING': self.activityType = Activity.Watching
            case 'LISTENING': self.activityType = Activity.Listening
    
    def setPresence(self, RPC: discordrpc.RPC):
        try:
            if self.thumbnail is None:
                RPC.set_activity(
                    name = self.name,
                    details = self.details,
                    act_type = self.activityType,
                    state = self.state
                )
            else:
                RPC.set_activity(
                    name = self.name,
                    details = self.details,
                    act_type = self.activityType,
                    state = self.state,
                    large_image = self.thumbnail
                )
        except discordrpc.RPCException as e:
            print(f'Error when trying to set status: {e}')
        except discordrpc.DiscordNotOpened:
            print(f"Failed to set activity: Discord is not open!")

@dataclass(kw_only = True)
class VideoPresence(Presence):
    state_url: str
    activityType: Activity = field(init = False)
    currentTime: int
    duration: int

    def __post_init__(self):
        self.activityType = Activity.Watching
    
    def setPresence(self, RPC: discordrpc.RPC):
        try:
            RPC.set_activity(
                name = self.name,
                details = self.details,
                state = self.state,
                act_type = self.activityType,
                **utils.progress_bar(self.currentTime, self.duration),
                large_image = self.thumbnail,
                details_url = self.state_url
            )
        except discordrpc.RPCException as e:
            print(f'Error when trying to set status: {e}')

    async def checkTime(self, websocket):
        # estimate video endTime by converting timeSent unix timestamp to seconds, adding remaining seconds in video, then adding 10s in case
        endTime = datetime.fromtimestamp((self.timeSent / 1000) + (self.duration - self.currentTime) + 5)

        now = datetime.now()

        endTimeSeconds = endTime - now
        endTimeSeconds = endTimeSeconds.total_seconds()

        # if the user navigates to a new tab in enabledPresences, this function's task will be cancelled
        # if the function times out (due to the user looping a video), request new tab info
        try:
            async with asyncio.timeout(endTimeSeconds):
                now = datetime.now()
                print(f'[{now.strftime("%I:%M %p")}]: Waiting for new tabs, or for timeout. Expected End Time: {endTime.strftime("%I:%M:%S %p")}\n')
                await asyncio.sleep(endTimeSeconds)
        except asyncio.CancelledError:
            now = datetime.now()
            print(f'\n[{now.strftime("%I:%M %p")}]: checkTime() timeout was cancelled (either new tabs were received, or seeking).\n')
        except TimeoutError:
            now = datetime.now()
            print(f'[{now.strftime("%I:%M %p")}]: Current time has passed expectedEndTime. Requesting new tab information.\n')
            
            response = json.dumps({'type': 'tabs', 'message': 'send updated tabs'})
            await websocket.send(response)

@dataclass
class MusicPresence(VideoPresence):
    activityType: Activity = field(init = False) 

    def __post_init__(self):
        self.activityType = Activity.Listening