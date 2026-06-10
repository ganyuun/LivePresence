import asyncio, keyring as kr, secrets, string
from nicegui import app, ui
from LivePresence_WebSocket import checkAuth, authentication, start_websocket_server

if kr.get_password('LivePresence', 'storageSecret') is None:
    alphabet = string.ascii_letters + string.digits + string.punctuation
    storageSecret = ''
    
    for i in range(16): storageSecret += secrets.choice(alphabet)

    kr.set_password('LivePresence', 'storageSecret', storageSecret)

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
        
        authResult = await authentication(clientID, clientSecret, redirectURI)

        if authResult == 'auth success':
            with container:
                ui.notify('Authenticated successfully!', type = 'positive')
            dialog.close()
            start_websocket_server()
        else:
            with container:
                ui.notify(f'{authResult}. Please try again.', type = 'negative')

    with ui.dialog().props('persistent') as dialog, ui.card():
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

    if authStatus == 'token active': await authentication(clientID, clientSecret, redirectURI)
    else: dialog.open()

@ui.page('/')
async def home():
    if app.storage.user.get('presencePriority') is None: 
        app.storage.user['presencePriority'] = ['YouTube', 'SoundCloud']
        presencePriority = app.storage.user['presencePriority']
    else: presencePriority = app.storage.user['presencePriority']

    if app.storage.user.get('enabledPresences') is None:
        app.storage.user['enabledPresences'] = presencePriority.copy()
    else: enabledPresences = app.storage.user['enabledPresences']

    await setup()

    def handleCheck(presence: str, add: bool):
        enabledPresences = app.storage.user['enabledPresences']
        
        if add is True and presence not in enabledPresences:
            enabledPresences.append(presence)
            
        elif add is False and presence in enabledPresences:
            enabledPresences.remove(presence)
        
        app.storage.user['enabledPresences'] = enabledPresences
        print(enabledPresences)

    with ui.list().classes('self-center w-full') as defaultPresences:
        for presence in presencePriority:
            with ui.item().classes('flex items-center justify-center w-full text-center py-2 my-4 h-12 rounded-md bg-blue-500 hover:bg-sky-700 cursor-grab active:cursor-grabbing'):
                ui.item_label(presence).classes('flex items-center justify-center')
                
                if presence in enabledPresences: ui.checkbox(value = True,  on_change = lambda e, presence = presence: handleCheck(presence, e.value))
                else: ui.checkbox(value = False, on_change = lambda e, presence = presence: handleCheck(presence, e.value))

    def presencesOnSort():
        order = [descendant.text for descendant in defaultPresences.descendants() if isinstance(descendant, ui.item_label)]
        print(order)
        app.storage.user['presencePriority'] = order
    
    defaultPresences.make_sortable(on_end = presencesOnSort)

if __name__ == "__main__":
    ui.run(dark = True, reload = False, storage_secret = kr.get_password('LivePresence', 'storageSecret'))