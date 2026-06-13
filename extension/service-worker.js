const websocket = new WebSocket("ws://localhost:8765/");
let presences = [];
let tabList = [];
let lastMessage = [];
let regex = { YouTube: new RegExp("^(\\(\\d+\\)\\s)|(\\s-\\sYouTube$)|(\\u200b)", "g"), SoundCloud: null, Miruro: null, urlRegex: new RegExp("^(https:\\/\\/www.)|(.com).*|(.tv).*", "g") };
let websocketActive = false;
let debounceTimer;

function connectWebSocket(websocket) {
    return new Promise((resolve, reject) => {
        websocket.onopen = () => {
            console.log("Connected to WebSocket successfully!")

            websocket.send(JSON.stringify({type: "hello", message: "ping"}));

            websocket.send(JSON.stringify({type: "enabledPresences"}));

            addChromeListeners();
        };

        websocket.onerror = (error) => {
            console.error("WebSocket connection error:", error);
            reject(error);
        };
    });
}

function addChromeListeners() {
    chrome.tabs.onUpdated.addListener(() => {
        debounceTimer = setTimeout(() => { getTabs(); }, 1000);
    });

    chrome.tabs.onRemoved.addListener((tabId, removeInfo) => {
        if (removeInfo.isWindowClosing === true) { websocket.send( JSON.stringify( {type: "tabs", message: []} )); }
        else {
            if (tabList.length > 0) {
                const filterIndex = tabList.findIndex(tab => tabId === tab.tabId);

                if (filterIndex !== -1) {
                    tabList.splice(filterIndex, 1);
                    console.log("Updated tabList:", tabList);
                    websocket.send( JSON.stringify( {type: "tabs", message: tabList} ));
                }
                else { console.log("tabList unchanged."); }
            }
            else { console.log("tabList unchanged."); }
        }
    })
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    console.log("Message received from", sender, ":", msg);

    if (msg.request === "ping") {
        if (websocketActive) { sendResponse({recipient: "popup.js", request: "Websocket active!"}) }
    }
});

async function notifyContent(recipient, request, tabId) {
    try {
        response = await chrome.tabs.sendMessage( tabId, {recipient: recipient, request: request} ); 
    } catch (error) { console.error("Unable to send message:", error); }
}

websocket.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data)

    if (msg.type === "hello") {
        websocketActive = true;
        console.log("Received hello:", msg);
    }

    if (msg.type === "enabledPresences") {
        const response = msg.message
        const hostNames = response.map( (dict) => dict.hostName );

        presences = {
            names: response.map( (dict) => dict.name ), 
            acceptedURLs: hostNames.map( (host) => `*://*.${host}/*` ), 
            videoType: response.map( dict => {if (dict.type === 'video') { return dict.name.toLowerCase() } else { return 'N/A' }} ),
            musicType: response.map( dict => {if (dict.type === 'music') { return dict.name.toLowerCase() } else { return 'N/A' }} )
        };

        presences.videoType = (presences.videoType).filter( presenceName => presenceName !== "N/A" )
        presences.musicType = (presences.musicType).filter( presenceName => presenceName !== "N/A" )
    }

    if (msg.type === 'tabs') { getTabs(true); }
});

const getVidInfo = (tabId, interval = 1000) => {
    return new Promise((resolve) => {
        const check = async () => {
            const [{result: result1}] = await chrome.scripting.executeScript({
                target: { tabId: tabId },
                func: () => document.querySelector('video')?.currentTime
            });
            
            const [{result: result2}] = await chrome.scripting.executeScript({
                        target: { tabId: tabId },
                        func: () => document.querySelector('video')?.duration
                    });

            let vidCurrentTime = result1;
            let vidDuration = result2;

            if (vidDuration != null && typeof vidCurrentTime != null) { resolve([vidCurrentTime, vidDuration]); }
            else { setTimeout(check, interval) }
        };
        check();
    });
}

async function getTabs(duplicates = false) {
    try {
        let activityType = ""

        let vidDuration;
        
        const tabs = await chrome.tabs.query({ url: presences.acceptedURLs });

        tabList = [];

        if (tabs.length > 0) {
            for (const tab of tabs) {
                if ( (presences.videoType).includes( (tab.url.replace(regex.urlRegex, "")) ) ) {
                    activityType = 'WATCHING';

                    const [vidCurrentTime, vidDuration] = await getVidInfo(tab.id);

                    console.log('vidDuration and vidCurrentTime:', vidCurrentTime, vidDuration);

                    if ((tab.url).includes("youtube")) {
                        tabList.push( {
                            'tabId': tab.id, 
                            'name': 'YouTube', 
                            'details': (tab.title).replace(regex.YouTube, ''), 
                            'url': (tab.url).replace(RegExp("&.*", "g"), ""), 
                            'activityType': activityType, 
                            'thumbnail': `https://img.youtube.com/vi/${(tab.url).replace(RegExp(".*(\\?v=)|(&).*", "g"), "")}/hqdefault.jpg`,
                            'currentTime': vidCurrentTime, 
                            'duration': vidDuration, 
                            'timeSent': Date.now()} );
                        continue
                    }
                }
                else if ( (presences.musicType).includes( (tab.url.replace(regex.urlRegex, "")) ) ) { activityType = 'LISTENING'; }
                else { activityType = 'PLAYING'; }

                tabList.push({
                    'tabId': tab.id, 
                    'details': tab.title, 
                    'url': tab.url, 
                    'activityType': activityType});
            }
        }

        if (duplicates === true) {
            websocket.send( JSON.stringify( {type: "tabs", message: tabList} ));
            console.log("Tabs sent");
            lastMessage = tabList;
        }
        else {
            const newDetails = tabList.map( (dict) => dict.details );
            let lastDetails = [];

            if (lastMessage !== []) { lastDetails = lastMessage.map( (dict) => dict.details ); }

            if (lastMessage === [] || JSON.stringify(newDetails) !== JSON.stringify(lastDetails)) {
                websocket.send( JSON.stringify( {type: "tabs", message: tabList} ));
                console.log("Tabs sent");
                lastMessage = tabList;
            }
            else { console.log("Duplicate message, not sent") }
        }
    } catch (error) { console.error("Error fetching tabs", error); }
}

connectWebSocket(websocket)