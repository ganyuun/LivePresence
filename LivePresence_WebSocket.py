import asyncio, websockets, json, requests, keyring as kr
from datetime import datetime, timedelta
from pypresence import AioPresence, AioClient, exceptions
from Presences import Activity, VideoActivity, MusicActivity

async def start_websocket_server():
    async with websockets.serve(hello, 'localhost', 8765) as server:
        await server.serve_forever()

async def hello(websocket):
    try:
        async for msgJSON in websocket:
            msg = json.loads(msgJSON)

            if msg.get('type') == 'hello': 
                response = json.dumps({'type': 'hello', 'message': 'pong'})
                await websocket.send(response)
                print('Sent hello!')
            elif msg.get('type') == 'presences':
                response = json.dumps({'type': 'enabledPresences', 'message': app.storage.user['enabledPresences']})
                await websocket.send(response)
                print('Sent enabled presences!')
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
        await setPresence()
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
                r = requests.post('https://discord.com/api/oauth2/token', data = data, headers = headers, auth = (clientID, clientSecret))
                r.raise_for_status()
                response = r.json()

                now = datetime.now()
                expiry = now + timedelta(seconds = int(response.get('expires_in')))

                kr.set_password('LivePresence', 'token', response.get('access_token'))
                kr.set_password('LivePresence', 'tokenSaveTime', now.strftime('%Y-%m-%d %H:%M:%S'))
                kr.set_password('LivePresence', 'tokenExpire', expiry.strftime('%Y-%m-%d %H:%M:%S'))
                kr.set_password('LivePresence', 'refreshToken', response.get('refresh_token'))

                await setPresence()
                return 'auth success'
            except requests.HTTPError:
                return 'Invalid Redirect URI'
        except exceptions.InvalidID:
            return 'Invalid Client ID'

async def setPresence():
    RPC = AioPresence(kr.get_password('LivePresence', 'clientID'))
    
    await RPC.connect()

    activity = Activity('LivePresence', 'PLAYING', 'Testing LivePresence', 1)

    print(
        await RPC.update(
            name = 'Testing LivePresence',
            details = "I genuinely hate this thing like actually",
            state = "I hate coding!!!!"
        )
    )

    while True:
        await asyncio.sleep(15)

async def main():
    clientID = kr.get_password('LivePresence', 'clientID')
    clientSecret = kr.get_password('LivePresence', 'clientSecret')
    redirectURI = kr.get_password('LivePresence', 'redirectURI')

    authStatus = checkAuth(clientID, clientSecret, redirectURI)

    if authStatus == 'token active' or authStatus == 'credentials saved, no auth': await authentication(clientID, clientSecret, redirectURI)
    else: import LivePresence_GUI

if __name__ == "__main__":
    asyncio.run(main())