import asyncio, keyring as kr, secrets, string, websockets, json, discordrpc
# from datetime import datetime
from nicegui import app, ui, background_tasks
# from discordrpc import utils, RPCException
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

    # temporary, will be changed into a task later if a video activity is used
    timePollingTask = None

    newActivity = None

    try:
        async for msgJSON in websocket:
            msgDict = json.loads(msgJSON)
            msgMessage = msgDict.get('message')

            match msgDict.get('type'):
                case 'hello':
                    if msgMessage != 'from extension popup' and msgMessage != 'keep alive': 
                        response = json.dumps({'type': 'hello', 'message': 'pong'})
                        print(f'Sent hello! {response}')
                    else: response = json.dumps({'type': 'hello', 'message': 'pong - silent'})
                    
                    await websocket.send(response)
                case 'enabledPresences':
                    enabledPresences = app.storage.general['enabledPresences']
                    presenceInfo = app.storage.general['presenceInfo']

                    filteredPresenceInfo = []

                    for x in range(len(enabledPresences)):
                        if enabledPresences[x] == presenceInfo[x].get('name'): filteredPresenceInfo.append(presenceInfo[x])

                    response = json.dumps({'type': 'enabledPresences', 'message': filteredPresenceInfo})
                    await websocket.send(response)
                    print(f'Sent enabled presences! {response}')
                case 'clear':
                    print('Status cleared on request from extension.')
                    RPC.clear()

                    if timePollingTask is not None: timePollingTask.cancel()
                case 'tabs':
                    if len(msgMessage) > 0:
                        # this check is mainly for video activities. duplicates = True when looping a video
                        # duplicates = False when the user navigated to a new video while the current one was playing
                        if msgMessage[0].get('duplicates') is False and timePollingTask is not None: timePollingTask.cancel() 

                        newActivity = createActivity(msgMessage)

                        if newActivity is None:
                            response = json.dumps({'type': 'tabs', 'message': 'send updated tabs'})
                            await websocket.send(response)
                        else:
                            newActivity.setPresence(RPC)

                            if newActivity.type in {'WATCHING', 'LISTENING'}:
                                timePollingTask = asyncio.create_task( newActivity.checkTime(websocket) )

                    else: RPC.clear()
                case 'checkRPC':
                    print('\nCheckRPC message received.')
                    response = json.dumps({'type': 'tabs', 'message': 'send updated tabs'})
                    await websocket.send(response)
                case 'seeked':
                    if newActivity is not None:
                        newActivity.currentTime = msgMessage
                        newActivity.setPresence(RPC)

                        if timePollingTask is not None and newActivity.type in {'WATCHING', 'LISTENING'}: 
                            timePollingTask.cancel()
                            timePollingTask = asyncio.create_task( newActivity.checkTime(websocket) )
                    else:
                        response = json.dumps({'type': 'tabs', 'message': 'send updated tabs'})
                        await websocket.send(response)
                case _:
                    response = json.dumps({'type': 'received', 'message': 'OK'})
                    await websocket.send(response)
                    print(f'Received: {msgDict}')
      
    except websockets.exceptions.ConnectionClosedOK:
        pass

def createActivity(tabs):
    presencePriority = app.storage.general['presencePriority']

    # assign priority to presences based on how they're ordered in the GUI
    for tab in tabs:
        try: tab.update( {'priority': presencePriority.index(tab.get("name"))} )
        except ValueError: tab.update( {'priority': -1} )
    
    highPriority = sorted(tabs, key = lambda x: x['priority'], reverse = True)[0]

    print('\nHighest priority activity:', highPriority)

    if highPriority['activityType'] in {'WATCHING', 'LISTENING'} and None in { highPriority.get('currentTime'), highPriority.get('duration') }: return None
    else:
        try:
            match highPriority.get('activityType'):
                case 'WATCHING':
                    activity = VideoPresence(
                        name = highPriority.get('name'), 
                        type = highPriority.get('activityType'),
                        details = highPriority.get('details'), 
                        currentTime = highPriority.get('currentTime'),
                        duration = highPriority.get('duration'),
                        thumbnail = highPriority.get('thumbnail', ''),
                        state_url = highPriority.get('url'),
                        timeSent = highPriority.get('timeSent')
                    )
                case 'LISTENING':
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
                case _:
                    activity = Presence(
                        name = highPriority.get('name'),
                        type = highPriority.get('activityType'),
                        details = highPriority.get('details'), 
                        timeSent = highPriority.get('timeSent')
                    )
        except ValueError:
            print('Invalid Activity Type provided by extension.')
            raise
    
        return activity

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
        app.storage.general['presencePriority'] = ['YouTube', 'SoundCloud', 'Miruro']

    if app.storage.general.get('enabledPresences') is None:
        app.storage.general['enabledPresences'] = ['YouTube', 'SoundCloud', 'Miruro']
    
    if app.storage.general.get('presenceInfo') is None:
        app.storage.general['presenceInfo'] = [
            {'name': 'YouTube', 'hostName': 'youtube.com', 'type': 'video'}, 
            {'name': 'SoundCloud', 'hostName': 'soundcloud.com', 'type': 'music'},
            {'name': 'Miruro', 'hostName': 'miruro.tv', 'type': 'video'}
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
