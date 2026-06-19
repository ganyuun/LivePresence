const websocket = new WebSocket("ws://localhost:8765/");
let presences = [];
let tabList = [];
let lastMessage = [];
let regex = { YouTube: new RegExp("^(\\(\\d+\\)\\s)|(\\s-\\sYouTube$)|(\\u200b)", "g"), SoundCloud: null, Miruro: null, urlRegex: new RegExp("^(https:\\/\\/www.)|(.com).*|(.tv).*", "g") };
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
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(async () => { 
            const tabs = await getTabs();
            if (tabs !== 'duplicate') {
                console.log("Tabs sent (duplicates = false):", tabs);
                websocket.send( JSON.stringify( {type: "tabs", message: tabs} ));
            }
        }, 1000);
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
    console.log("Service worker received message from", sender.id, ":", msg);

    if (msg.request === "ping") {
        try {
            websocket.send(JSON.stringify({type: "hello", message: "from extension popup"}));
            sendResponse({recipient: "popup.js", request: "pong"});
        } catch (error) {
            console.error("Unable to send message:", error)
        }
    }
    else if (msg.request === 'clear') {
        try {
            websocket.send( JSON.stringify({type: "clear", message: "clear"}) );
            console.log("Sent message to Python script to clear status:", {type: "clear", message: "clear"})
        }
        catch (error) { console.error("Unable to send message:", error) }
    }
});

websocket.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data)

    if (msg.type === "hello") { console.log("Received hello:", msg); }

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

    if (msg.type === 'tabs') {
        clearTimeout(debounceTimer);

        debounceTimer = setTimeout(async () => { 
            const tabs = await getTabs(true);
            console.log("Tabs sent (duplicates = true):", tabs);
            websocket.send( JSON.stringify( {type: "tabs", message: tabs} ));
        }, 1000);
    }
});

const getVidInfo = (tabId) => {
    return new Promise((resolve) => {
        let interval = 1000;

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

            if (typeof vidDuration != "undefined" && typeof vidCurrentTime != "undefined") { resolve([vidCurrentTime, vidDuration]); }
            else { setTimeout(check, interval); }
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

        console.log("Original tabs:", tabs)

        if (tabs.length > 0) {
            for (const tab of tabs) {
                let tabName = tab.url.replace(regex.urlRegex, "");

                if ( presences.videoType.includes(tabName) ) {
                    activityType = 'WATCHING';

                    const [vidCurrentTime, vidDuration] = await getVidInfo(tab.id);

                    if (tab.url.includes("youtube.com/watch")) {
                        tabList.push( {
                            'tabId': tab.id, 
                            'name': 'YouTube', 
                            'details': (tab.title).replace(regex.YouTube, ''), 
                            'url': (tab.url).replace(RegExp("&.*", "g"), ""), 
                            'activityType': activityType, 
                            'thumbnail': `https://img.youtube.com/vi/${(tab.url).replace(RegExp(".*(\\?v=)|(&).*", "g"), "")}/hqdefault.jpg`,
                            'currentTime': vidCurrentTime, 
                            'duration': vidDuration, 
                            'timeSent': Date.now(),
                            'active': tab.active,
                            'audible': tab.audible } );
                        continue
                    }
                }
                else if ( presences.musicType.includes(tabName)) { activityType = 'LISTENING'; }
                else { activityType = 'PLAYING'; }

                tabList.push({
                    'tabId': tab.id, 
                    'details': tab.title, 
                    'url': tab.url, 
                    'activityType': activityType});
            }
        }

        if (duplicates === true) {
            lastMessage = tabList;
            return tabList;
        }
        else {
            const newDetails = tabList.map( (dict) => dict.details );
            let lastDetails = [];

            if (lastMessage.length > 0) { lastDetails = lastMessage.map( (dict) => dict.details ); }
            
            if (lastMessage.length === 0 || JSON.stringify(newDetails) !== JSON.stringify(lastDetails)) {
                lastMessage = tabList;
                return tabList;
            }
            else { 
                console.log("Duplicate message, not sent:", tabList)
                return "duplicate";
            }
        }
    } catch (error) { 
        console.error("Error fetching tabs", error);
        return [];
    }
}

connectWebSocket(websocket)