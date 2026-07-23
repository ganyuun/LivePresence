import asyncio, keyring as kr, secrets, string, websockets, json, discordrpc, pystray
from nicegui import app, ui, background_tasks
from Presences import Presence, VideoPresence, MusicPresence
from PIL import Image

RPC = None
icon = None # for system tray icon
rpcActive = False # default value, updated on startup
shutdownEvent = asyncio.Event()
serverStarted = False
connectedClients = set()

def getRpcStatus():
    global rpcActive
    return rpcActive

def updateRpcActive(icon, item):
    global rpcActive
    rpcActive = not item.checked

async def createIcon(shutdownEvent: asyncio.Event):
    global icon

    def exit():
        shutdownEvent.set()

    favicon = Image.open('favicon.ico')
    
    if pystray.Icon.HAS_MENU:
        menu = pystray.Menu(
            pystray.MenuItem('RPC Active', updateRpcActive, checked = lambda item: rpcActive), 
            pystray.MenuItem('Clear Status', clearActivity),
            pystray.MenuItem('Exit', exit)
        )
    else: menu = None

    icon = pystray.Icon('LivePresence', icon = favicon, menu = menu)
    icon.run_detached()

async def sendEnabledPresences():
    enabledPresences = app.storage.general['enabledPresences']
    presenceInfo = app.storage.general['presenceInfo']

    filteredPresenceInfo = []

    for site in enabledPresences:
        if presenceInfo.get(site) is not None: filteredPresenceInfo.append(presenceInfo.get(site))

    response = json.dumps({'type': 'enabledPresences', 'message': filteredPresenceInfo})
    
    for websocket in connectedClients:
        await websocket.send(response)

    print('Sent enabled presences!', response, '\n')

async def startWebsocket():
    global serverStarted
    serverStarted = True

    async with websockets.serve(hello, 'localhost', 8765) as server:
        await server.serve_forever()
    
    print("Websocket started")

async def hello(websocket):
    global RPC

    connectedClients.add(websocket)

    RPC = discordrpc.RPC(app_id = clientID)

    # temporary, will be changed into a task later if a video/music activity is used
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
                    await sendEnabledPresences()
                case 'clear':
                    print('Status cleared on request from extension.')
                    RPC.clear()

                    if timePollingTask is not None: timePollingTask.cancel()
                case 'tabs':
                    if getRpcStatus(): # from the system tray
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

                        else: 
                            # prevents script from automatically trying to clear status if it's already cleared
                            if newActivity is not None:
                                match newActivity.name:
                                    case None: pass
                                    case _:
                                        newActivity.name = None
                                        RPC.clear()                    
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
                case 'exit':
                    print('NiceGUI shutting down.')
                    app.shutdown()
                case _:
                    response = json.dumps({'type': 'received', 'message': 'OK'})
                    await websocket.send(response)
                    print(f'Received: {msgDict}')
    except websockets.exceptions.ConnectionClosedOK: pass
    finally: connectedClients.remove(websocket)

def createActivity(tabs):
    presencePriority = app.storage.general['presencePriority']

    # assign priority to presences based on how they're ordered in the GUI
    for tab in tabs:
        try: tab.update( {'priority': presencePriority.index(tab.get("name"))} )
        except ValueError: tab.update( {'priority': -1} )
    
    highPriority = sorted(tabs, key = lambda x: x['priority'], reverse = True)[0]

    print('Highest priority activity:', highPriority, '\n')

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

def clearActivity():
    if RPC is not None:
        RPC.clear()

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

    async def handleCheck(presence: str, add: bool):
        enabledPresences = app.storage.general['enabledPresences']
        
        if add is True and presence not in enabledPresences:
            enabledPresences.append(presence)
            
        elif add is False and presence in enabledPresences:
            enabledPresences.remove(presence)
        
        app.storage.general['enabledPresences'] = enabledPresences
        
        await sendEnabledPresences()
    
    def handleSwitch(switch: str, toggle: bool):
        app.storage.general['settings'][switch] = toggle

    with ui.expansion('Presences', value = True).classes('self-center w-full'):
        with ui.list().classes('self-center w-full') as defaultPresences:
            for presence in presencePriority:
                with ui.item().classes('flex items-center justify-center w-full text-center py-2 my-4 h-12 rounded-md bg-blue-500 hover:bg-sky-700 cursor-grab active:cursor-grabbing'):
                    ui.item_label(presence).classes('flex items-center justify-center')
                    
                    if presence in enabledPresences: ui.checkbox(value = True,  on_change = lambda e, presence = presence: handleCheck(presence, e.value))
                    else: ui.checkbox(value = False, on_change = lambda e, presence = presence: handleCheck(presence, e.value))
    with ui.expansion('Settings').classes('self-center w-full'):
        s1 = ui.switch('RPC Broadcast Enabled on Startup', value = app.storage.general.get('settings').get('rpc status'), on_change = lambda: handleSwitch('rpc status', s1.value))

    def presencesOnSort():
        order = [descendant.text for descendant in defaultPresences.descendants() if isinstance(descendant, ui.item_label)]
        print(order)
        app.storage.general['presencePriority'] = order
    
    defaultPresences.make_sortable(on_end = presencesOnSort)

@app.on_startup
async def onStartup():
    global rpcActive

    # presencePriority needs to be updated whenever new supported sites are added
    if app.storage.general.get('presencePriority') is None: 
        app.storage.general['presencePriority'] = ['YouTube', 'SoundCloud', 'Miruro', 'LoL Esports', 'Twitch']
    else:
        prioritySet = set(app.storage.general['presencePriority'])
        infoSet = set(app.storage.general['presenceInfo'].keys())

        if prioritySet != infoSet: app.storage.general['presencePriority'].extend( infoSet - prioritySet )

    if app.storage.general.get('enabledPresences') is None:
        app.storage.general['enabledPresences'] = ['YouTube', 'SoundCloud', 'Miruro']
    
    if app.storage.general.get('settings') is None:
        app.storage.general['settings'] = {
            'rpc status': False
        }
    else:
        # this check is unnecessary for now, but is here in case additional settings are added in future updates
        currentSettings = app.storage.general.get('settings')
        updatedSettings = {'rpc status': False}

        if len(updatedSettings.keys()) > len(currentSettings.keys()):
            currentKeys = currentSettings.keys()

            for key in updatedSettings:
                if key not in currentKeys:
                    currentSettings[key] = updatedSettings[key]
            
            app.storage.general['settings'] = currentSettings

    rpcActive = app.storage.general.get('settings', False).get('rpc status', False)
    
    presenceInfo = app.storage.general.get('presenceInfo')
    
    if presenceInfo is None:
        app.storage.general['presenceInfo'] = {
            'YouTube': {'name': 'YouTube', 'hostName': 'youtube.com', 'type': 'video'},
            'SoundCloud': {'name': 'SoundCloud', 'hostName': 'soundcloud.com', 'type': 'music'},
            'Miruro': {'name': 'Miruro', 'hostName': 'miruro.tv', 'type': 'video'},
            'LoL Esports': {'name': 'LoL Esports', 'hostName': 'lolesports.com', 'type': 'stream'},
            'Twitch': {'name': 'Twitch', 'hostName': 'twitch.tv', 'type': 'stream'}
        }
    else:
        if set(presenceInfo.keys()) != {'YouTube', 'SoundCloud', 'Miruro', 'LoL Esports', 'Twitch'}:
            app.storage.general['presenceInfo'] = {
            'YouTube': {'name': 'YouTube', 'hostName': 'youtube.com', 'type': 'video'},
            'SoundCloud': {'name': 'SoundCloud', 'hostName': 'soundcloud.com', 'type': 'music'},
            'Miruro': {'name': 'Miruro', 'hostName': 'miruro.tv', 'type': 'video'},
            'LoL Esports': {'name': 'LoL Esports', 'hostName': 'lolesports.com', 'type': 'stream'},
            'Twitch': {'name': 'Twitch', 'hostName': 'twitch.tv', 'type': 'stream'}
        }
    
    if serverStarted is False and kr.get_password('LivePresence', 'clientID') is not None:
        background_tasks.create(startWebsocket())
        
        background_tasks.create(createIcon(shutdownEvent))

        await shutdownEvent.wait()
        
        app.shutdown()
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
    else: 
        ui.run(dark = True, reload = False, storage_secret = storageSecret, show = False)
