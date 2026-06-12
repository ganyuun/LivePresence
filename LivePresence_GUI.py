import asyncio, keyring as kr, secrets, string, websockets, json, httpx
from nicegui import app, ui, background_tasks
from datetime import datetime, timedelta
from pypresence import AioPresence, AioClient, exceptions
from Presences import Activity, VideoActivity, MusicActivity

serverStarted = False

async def startWebsocket():
    global serverStarted
    serverStarted = True

    async with websockets.serve(hello, 'localhost', 8765) as server:
        await server.serve_forever()
        print("Websocket started")

async def hello(websocket):
    try:
        async for msgJSON in websocket:
            msg = json.loads(msgJSON)

            if msg.get('type') == 'hello': 
                response = json.dumps({'type': 'hello', 'message': 'pong'})
                await websocket.send(response)
                print(f'Sent hello! {response}')
            elif msg.get('type') == 'enabledPresences':
                enabledPresences = app.storage.general['enabledPresences']

                response = json.dumps({'type': 'enabledPresences', 'message': enabledPresences})
                await websocket.send(response)
                print(f'Sent enabled presences! {response}')
            elif msg.get('type') == 'tabs':
                presencePriority = app.storage.general['presencePriority']
                activities = msg.get('message')

                for activity in activities:
                    try:
                        activity.update( {'priority': presencePriority.index(activity.get("name"))} )
                    except ValueError:
                        activity.update( {'priority': -1} )
                
                highPriority = sorted(activities, key = lambda x: x['priority'], reverse = True)[0]

                print(highPriority)

                if highPriority.get('activityType') == 'WATCHING':
                    newActivity = VideoActivity(
                        name = highPriority.get('name'), 
                        details = highPriority.get('details'), 
                        duration = highPriority.get('duration'),
                        type = highPriority.get('activityType'),
                        state_url = highPriority.get('url')
                    )
                await setPresence(newActivity)
            else:
                response = json.dumps({'type': 'received', 'message': 'OK'})
                await websocket.send(response)
                print(f'Received: {msg}')
    except websockets.exceptions.ConnectionClosedOK:
        pass

def checkAuth(clientID: str = None, clientSecret: str = None, redirectURI: str = None):
    if None not in [clientID, clientSecret, redirectURI]:
        if None in [kr.get_password('LivePresence', 'token'), kr.get_password('LivePresence', 'tokenExpire')]:
            return 'credentials saved, no auth'
        else:
            tokenExpiry = kr.get_password('LivePresence', 'tokenExpire')

            if datetime.now() > datetime.strptime(tokenExpiry, '%Y-%m-%d %H:%M:%S'): return 'token expired'
            else: return 'token active'
    else: return 'no credentials saved'

async def authentication(clientID: str, clientSecret: str, redirectURI: str, refreshToken: str = None):
    loop = asyncio.get_running_loop()

    client = AioClient(clientID, loop = loop)
    await client.start()

    if checkAuth(clientID, clientSecret, redirectURI) == 'token active':
        await client.authenticate(kr.get_password('LivePresence', 'token'))
        return 'auth success'
    else:
        try:
            auth = await client.authorize(clientID, ['rpc'])
            code = auth.get('data').get('code')

            if refreshToken is None:
                data = {
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': redirectURI
                }
            else:
                data = {
                    'grant_type': 'refresh_token',
                    'refresh_token': refreshToken
                }
            
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}

            try:
                r = httpx.post('https://discord.com/api/oauth2/token', data = data, headers = headers, auth = (clientID, clientSecret))
                r.raise_for_status()
                response = r.json()

                print(r.text)

                now = datetime.now()
                expiry = now + timedelta(seconds = int(response.get('expires_in')))

                kr.set_password('LivePresence', 'token', response.get('access_token'))
                kr.set_password('LivePresence', 'tokenSaveTime', now.strftime('%Y-%m-%d %H:%M:%S'))
                kr.set_password('LivePresence', 'tokenExpire', expiry.strftime('%Y-%m-%d %H:%M:%S'))
                kr.set_password('LivePresence', 'refreshToken', response.get('refresh_token'))

                return 'auth success'
            except httpx.HTTPError:
                return 'Invalid Redirect URI'
        except exceptions.InvalidID:
            return 'Invalid Client ID'

async def setPresence(activity: Activity):
    RPC = AioPresence(kr.get_password('LivePresence', 'clientID'))
    
    await RPC.connect()

    if (activity.start):
        print(
            await RPC.update(
                name = activity.name,
                details = activity.details,
                start = activity.start,
                end = activity.end,
            )
        )
    else:
        print(
            await RPC.update(
                name = activity.name,
                details = activity.details,
            )
        )

    # while True:
    await asyncio.sleep(15)

async def setup():
    clientID = kr.get_password('LivePresence', 'clientID')
    clientSecret = kr.get_password('LivePresence', 'clientSecret')
    redirectURI = kr.get_password('LivePresence', 'redirectURI')

    authStatus = checkAuth(clientID, clientSecret, redirectURI)
    print(authStatus)

    container = ui.row()

    async def save(clientID: str, clientSecret: str, redirectURI: str):
        kr.set_password('LivePresence', 'clientID', clientID)
        kr.set_password('LivePresence', 'clientSecret', clientSecret)
        kr.set_password('LivePresence', 'redirectURI', redirectURI)

        with container: ui.notify('Saved! Now authenticating...', type = 'info')
        
        authResult = asyncio.create_task(authentication(clientID, clientSecret, redirectURI))

        print(authResult)

        if authResult == 'auth success':
            with container:
                ui.notify('Authenticated successfully!', type = 'positive')
            dialog.close()
        else:
            with container:
                ui.notify(f'{authResult}. Please try again.', type = 'negative')

    with ui.dialog(value = True).props('persistent') as dialog, ui.card():
        ui.markdown('''
            No token was detected. Please enter your application's client ID and client secret from the [Discord Developer Portal](https://discord.com/developers/home) to continue using LivePresence.
            
            For the redirect URI, make sure to enter it in the Redirects section of your app in the Developer Portal, and enter the same one here. Use `http://localhost:(any port)/(some endpoint)/`.
        ''')

        with ui.row():
            inputClientID = ui.input(label = 'Client ID', value = kr.get_password('LivePresence', 'clientID'), validation = {'Number input only': lambda v: v.isdigit() if v else False, 'Client ID must be 18 or 19 chars long': lambda v: len(v) > 17 and len(v) < 20}, on_change = lambda: saveButtonValidation())
            inputClientSecret = ui.input(label = 'Client Secret', value = kr.get_password('LivePresence', 'clientSecret'), password = True, on_change = lambda: saveButtonValidation)
            inputRedirectURI = ui.input(label = 'Redirect URI', value = kr.get_password('LivePresence', 'redirectURI'), validation = {'Must use localhost': lambda v: 'http://localhost:' in v}, on_change = lambda: saveButtonValidation())
        
        saveButton = ui.button('Authenticate', on_click = lambda: save(inputClientID.value, inputClientSecret.value, inputRedirectURI.value)).classes('justify-center')
        
        if None in [inputClientID.value, inputClientSecret.value, inputRedirectURI.value]: saveButton.disable()
    
    def saveButtonValidation():
        if inputClientID.value.isdigit() and 'http://localhost:' in inputRedirectURI.value: saveButton.enable()
        else: saveButton.disable()

@ui.page('/')
async def home():
    presencePriority = app.storage.general['presencePriority']
    enabledPresences = app.storage.general['enabledPresences']
    print(enabledPresences)

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
        app.storage.general['enabledPresences'] = [
            {'name': 'YouTube', 'hostName': 'youtube.com', 'type': 'video'}, 
            {'name': 'SoundCloud', 'hostName': 'soundcloud.com', 'type': 'music'}
        ]

    if authStatus == 'token active':
        authResult = await authentication(clientID, clientSecret, redirectURI)
        print(authResult)

        if authResult == 'auth success':
            if serverStarted is False: background_tasks.create(startWebsocket())
            else: print('Not starting server, already active')
    else: await setup()

if __name__ == "__main__":
    clientID = kr.get_password('LivePresence', 'clientID')
    clientSecret = kr.get_password('LivePresence', 'clientSecret')
    redirectURI = kr.get_password('LivePresence', 'redirectURI')

    authStatus = checkAuth(clientID, clientSecret, redirectURI)
    storageSecret = kr.get_password('LivePresence', 'storageSecret')

    print(authStatus)
    
    if storageSecret is None:
        storageSecret = ''
        
        for i in range(16): storageSecret += secrets.choice(string.ascii_letters)

        kr.set_password('LivePresence', 'storageSecret', storageSecret)
    
    if authStatus == 'token active':
        ui.run(dark = True, reload = False, storage_secret = storageSecret, show = False)
    else: ui.run(dark = True, reload = False, storage_secret = storageSecret)
