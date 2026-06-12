import { updateElements } from "./websocket.js";

const websocket = new WebSocket("ws://localhost:8765/");
let presences = [];
let tabList = [];
let lastMessage = [];
let regex = { YouTube: new RegExp("^(\\(\\d+\\)\\s)|(\\s-\\sYouTube$)", "g"), SoundCloud: null, Miruro: null, urlRegex: new RegExp("^(https:\\/\\/www.)|(.com).*|(.tv).*", "g") };
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
    chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
        clearTimeout(debounceTimer);

        let activeInfo = {id: tab.id, title: tab.title || "Loading", url: tab.url}

        debounceTimer = setTimeout(() => { getTabs(activeInfo); }, 1000);

        console.log("activeInfo", activeInfo)
    });

    chrome.tabs.onRemoved.addListener((tabId, removeInfo) => {
        console.log("onRemoved Listener removeInfo:", removeInfo)

        if (removeInfo.isWindowClosing === true) { websocket.send( JSON.stringify( {type: "tabs", message: []} )); }
        else {
            if (tabList.length > 0) {
                const filterIndex = tabList.findIndex(tab => tabId === tab.tabId);
                console.log("filterIndex in onRemoved:", filterIndex);

                if (filterIndex !== -1) {
                    tabList.splice(filterIndex, 1);
                    console.log("Updated tabList:", tabList);
                    websocket.send( JSON.stringify( {type: "tabs", message: tabList} ));
                }
                else { console.log("tabList unchanged:", tabList); }
            }
            else { console.log("tabList unchanged:", tabList); }
        }
    })
}

websocket.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data)

    if (msg.type === "hello") {
        websocketActive = true;
        console.log("Received hello:", msg);
        updateElements('ping');
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

        console.log("Presences:", presences)
    }
});

async function getTabs(activeInfo) {
    try {
        let activityType = ""
        
        const tabs = await chrome.tabs.query({ url: presences.acceptedURLs });

        tabList = [];

        if (tabs.length > 0) { 
            tabs.forEach( 
                (tab) => {
                    if ( (presences.videoType).includes( (tab.url.replace(regex.urlRegex, "")) ) ) { activityType = "WATCHING"; }
                    else if ( (presences.musicType).includes( (tab.url.replace(regex.urlRegex, "")) ) ) { activityType = "LISTENING" }
                    else { activityType = "PLAYING" }

                    if ((tab.title).includes("- YouTube")) { tabList.push( {'tabId': tab.id, 'name': 'YouTube', 'details': (tab.title).replace(regex.YouTube, ""), 'url': (tab.url).replace(RegExp("&.*", "g"), ""), 'activityType': activityType} ); }
                    else { tabList.push({'tabId': tab.id, 'details': tab.title, 'url': tab.url, 'activityType': activityType}); }
                }
            ); 
        }
        const newDetails = tabList.map( (dict) => dict.details );
        let lastDetails = [];

        if (lastMessage !== []) { lastDetails = lastMessage.map( (dict) => dict.details ); }

        console.log("newDetails/lastDetails", newDetails, lastDetails);

        if (lastMessage === [] || JSON.stringify(newDetails) !== JSON.stringify(lastDetails)) {
            websocket.send( JSON.stringify( {type: "tabs", message: tabList} ));
            console.log("Tabs sent", tabList);
            lastMessage = tabList;
        }
        else { console.log("Duplicate message, not sent") }
    } catch (error) { console.error("Error fetching tabs", error); }
}

connectWebSocket(websocket)