import asyncio, keyring as kr, secrets, string, websockets, json, discordrpc
from datetime import datetime
from nicegui import app, ui, background_tasks
from discordrpc import utils, RPCException
from Presences import Presence, VideoPresence, MusicPresence

serverStarted = False

# websockets.exceptions.ConnectionClosedError: sent 1011 (internal error) keepalive ping timeout; no close frame received
# will try except connectionclosed later, make websocket reconnect if it runs into issues
async def startWebsocket():
    global serverStarted
    serverStarted = True

    async with websockets.serve(hello, 'localhost', 8765) as server:
        await server.serve_forever()
    
    print("Websocket started")

async def hello(websocket):
    RPC = discordrpc.RPC(app_id = clientID)
    newTabsEvent = asyncio.Event()

    try:
        async for msgJSON in websocket:
            msgDict = json.loads(msgJSON)

            msgType = msgDict.get('type')
            msgMessage = msgDict.get('message')

            if msgType == 'hello': 
                response = json.dumps({'type': 'hello', 'message': 'pong'})
                await websocket.send(response)

                if msgMessage != 'from extension popup': print(f'Sent hello! {response}')
            elif msgType == 'enabledPresences':
                enabledPresences = app.storage.general['enabledPresences']
                presenceInfo = app.storage.general['presenceInfo']

                filteredPresenceInfo = []

                for x in range(len(enabledPresences)):
                    if enabledPresences[x] == presenceInfo[x].get('name'):
                        filteredPresenceInfo.append(presenceInfo[x])

                response = json.dumps({'type': 'enabledPresences', 'message': filteredPresenceInfo})
                await websocket.send(response)
                print(f'Sent enabled presences! {response}')
            elif msgType == 'clear':
                print('Status cleared on request from extension.')
                RPC.clear()
            elif msgType == 'tabs':
                newTabsEvent.set()

                if len(msgMessage) > 0:
                    newActivity = createActivity(msgMessage)

                    expectedEndTime = datetime.fromtimestamp((newActivity.timeSent / 1000) + (newActivity.duration - newActivity.currentTime))
                    timePollingTask = asyncio.create_task(checkTime(expectedEndTime, newTabsEvent))
                    result = await timePollingTask

                    setPresence(newActivity, RPC)

                    if result == 1:
                        print('timePollingTask returned 1')
                        response = json.dumps({'type': 'tabs', 'message': 'send updated tabs'})
                        await websocket.send(response)
                else: RPC.clear()
            else:
                response = json.dumps({'type': 'received', 'message': 'OK'})
                await websocket.send(response)
                print(f'Received: {msgDict}')
    except websockets.exceptions.ConnectionClosedOK:
        pass

def createActivity(tabs):
    presencePriority = app.storage.general['presencePriority']

    # assign priority to presences based on how they're ordered in the GUI
    # if a Watching/Listening presence is open, reduce priority by 1 if it's muted (ex. if you have multiple YouTube tabs open, display the one that's actually playing)
    for tab in tabs:
        tabType = tab.get('activityType')

        try:
            if (tabType in ['WATCHING', 'LISTENING'] and (tab.get('audible') == True or tab.get('active') == True)) or (tabType not in ['WATCHING', 'LISTENING']):
                tab.update( {'priority': presencePriority.index(tab.get("name"))} )
            elif tabType in ['WATCHING', 'LISTENING'] and tab.get('audible') == False:
                tab.update( {'priority': presencePriority.index(tab.get("name")) - 1} )
        except ValueError: 
            tab.update( {'priority': -1} )
    
    highPriority = sorted(tabs, key = lambda x: x['priority'], reverse = True)[0]

    print('Highest priority activity:', highPriority)

    if highPriority.get('activityType') == 'WATCHING':
        currentTime = highPriority.get('currentTime')
        
        # allowing a little bit of desync in case currentTime is ahead of actual time
        if currentTime > 5: currentTime -= 5

        activity = VideoPresence(
            name = highPriority.get('name'), 
            type = highPriority.get('activityType'),
            details = highPriority.get('details'), 
            currentTime = currentTime,
            duration = highPriority.get('duration'),
            thumbnail = highPriority.get('thumbnail', ''),
            state_url = highPriority.get('url'),
            timeSent = highPriority.get('timeSent')
        )
    elif highPriority.get('activityType') == 'LISTENING':
        activity = MusicPresence(
            name = highPriority.get('name'), 
            type = highPriority.get('activityType'),
            details = highPriority.get('details'), 
            currentTime = highPriority.get('currentTime'),
            duration = highPriority.get('duration'),
            thumbnail = highPriority.get('thumbnail', ''),
            state_url = highPriority.get('url'),
            timeSent = highPriority.get('timeSent')
        )
    else:
        activity = Presence(
            name = highPriority.get('name'),
            type = highPriority.get('activityType'),
            details = highPriority.get('details'), 
            timeSent = highPriority.get('timeSent')
        )
    
    return activity

def setPresence(presence: Presence, RPC: discordrpc.RPC):
    try:
        if (presence.type in ['WATCHING', 'LISTENING']):
            RPC.set_activity(
                state = presence.name,
                details = presence.details,
                act_type = presence.activityType,
                **utils.ProgressBar(presence.currentTime, presence.duration),
                large_image = presence.thumbnail,
                status_type = presence.statusDisplayType,
                details_url = presence.state_url
            )
        else:
            RPC.set_activity(
                state = presence.name,
                details = presence.details,
                act_type = presence.activityType,
                status_type = presence.statusDisplayType
            )
    except RPCException as e:
        print(f'Error when trying to set status: {e}')

async def checkTime(endTime, event: asyncio.Event):
    print("Expected End Time:", endTime.strftime("%I:%M:%S"))

    now = datetime.now()

    endTimeSeconds = endTime - now
    endTimeSeconds = endTimeSeconds.total_seconds()

    # if the user navigates to a new tab in enabledPresences, it triggers the newTabEvent
    # returning 0 prevents checkTime() from asking for new tabs thru websocket
    try:
        async with asyncio.timeout(endTimeSeconds):
            now = datetime.now()
            await event.wait()
            print(f'[{now.strftime("%I:%M %p")}]: Received new tabs, cancelling checkTime() timeout.')
            event.clear()
            return 0
    except TimeoutError:
        now = datetime.now()
        print(f'[{now.strftime("%I:%M %p")}]: Current time has passed expectedEndTime. Requesting new tab information.')
        return 1

async def setup():
    container = ui.row()

    async def save(clientID: str):
        kr.set_password('LivePresence', 'clientID', clientID)

        with container: ui.notify('Saved! Now authenticating...', type = 'info')

        try:
            discordrpc.RPC(app_id = inputClientID.value)

            with container:
                ui.notify('LivePresence connected to Discord successfully!', type = 'positive')
            dialog.close()
        except discordrpc.exceptions.RPCException as e:
            with container:
                ui.notify(f'{e}. Please try again.', type = 'negative')
            
    with ui.dialog(value = True).props('persistent') as dialog, ui.card():
        ui.label('''No Client ID was detected. Please enter your application's client ID 
                from the [Discord Developer Portal](https://discord.com/developers/home) to 
                continue using LivePresence.''')

        inputClientID = ui.input(label = 'Client ID', value = kr.get_password('LivePresence', 'clientID'), validation = {'Number input only': lambda v: v.isdigit() if v else False, 'Client ID must be 18 or 19 chars long': lambda v: len(v) > 17 and len(v) < 20}, on_change = lambda: saveButtonValidation())
        
        saveButton = ui.button('Save', on_click = lambda: save(inputClientID.value)).classes('justify-center')
        
        if inputClientID.value is None: saveButton.disable()
    
    def saveButtonValidation():
        if inputClientID.value.isdigit(): saveButton.enable()
        else: saveButton.disable()

@ui.page('/')
async def home():
    presencePriority = app.storage.general['presencePriority']
    enabledPresences = app.storage.general['enabledPresences']
    print("enabledPresences:", enabledPresences)

    def handleCheck(presence: str, add: bool):
        enabledPresences = app.storage.general['enabledPresences']
        
        if add is True and presence not in enabledPresences:
            enabledPresences.append(presence)
            
        elif add is False and presence in enabledPresences:
            enabledPresences.remove(presence)

    with ui.list().classes('self-center w-full') as defaultPresences:
        for presence in presencePriority:
            with ui.item().classes('flex items-center justify-center w-full text-center py-2 my-4 h-12 rounded-md bg-blue-500 hover:bg-sky-700 cursor-grab active:cursor-grabbing'):
                ui.item_label(presence).classes('flex items-center justify-center')
                
                if presence in enabledPresences: ui.checkbox(value = True,  on_change = lambda e, presence = presence: handleCheck(presence, e.value))
                else: ui.checkbox(value = False, on_change = lambda e, presence = presence: handleCheck(presence, e.value))

    def presencesOnSort():
        order = [descendant.text for descendant in defaultPresences.descendants() if isinstance(descendant, ui.item_label)]
        print(order)
        app.storage.general['presencePriority'] = order
    
    defaultPresences.make_sortable(on_end = presencesOnSort)

@app.on_startup
async def onStartup():
    if app.storage.general.get('presencePriority') is None: 
        app.storage.general['presencePriority'] = ['YouTube', 'SoundCloud']

    if app.storage.general.get('enabledPresences') is None:
        app.storage.general['enabledPresences'] = ['YouTube', 'SoundCloud']
    
    if app.storage.general.get('presenceInfo') is None:
        app.storage.general['presenceInfo'] = [
            {'name': 'YouTube', 'hostName': 'youtube.com', 'type': 'video'}, 
            {'name': 'SoundCloud', 'hostName': 'soundcloud.com', 'type': 'music'}
        ]
    
    if serverStarted is False and kr.get_password('LivePresence', 'clientID') is not None:
        background_tasks.create(startWebsocket())
    elif kr.get_password('LivePresence', 'clientID') is None:
        print('Not starting Websocket, clientID not found.')
        await setup()
    else: 
        print('Not starting Websocket, already active')

if __name__ == "__main__":
    clientID = kr.get_password('LivePresence', 'clientID')
    storageSecret = kr.get_password('LivePresence', 'storageSecret')
    
    if storageSecret is None:
        storageSecret = ''
        
        for i in range(16): storageSecret += secrets.choice(string.ascii_letters)

        kr.set_password('LivePresence', 'storageSecret', storageSecret)
    
    if clientID is None:
        ui.run(dark = True, reload = False, storage_secret = storageSecret)
    else: ui.run(dark = True, reload = False, storage_secret = storageSecret, show = False)
