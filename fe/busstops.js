(function () {
    "use strict";

    if (location.protocol !== 'https:' && location.hostname !== 'localhost') {
        location.href = 'https:' + window.location.href.substring(window.location.protocol.length);
    }

    var l_map;
    var marker_group;
    var coords = {latitude: 51.6754966, longitude: 39.2088823}

    var lastbusquery = document.getElementById('lastbusquery')
    var station_query = document.getElementById('station_query')
    var station_name = document.getElementById('station_name')

    var timer_id = 0
    var timer_stop_id = 0

    var info = document.getElementById('info')
    var businfo = document.getElementById('businfo')
    var lastbus = document.getElementById('lastbus')
    var nextbus_loading = document.getElementById('nextbus_loading')
    var lastbus_loading = document.getElementById('lastbus_loading')
    var cb_show_labels = document.getElementById('cb_show_labels')
    var cb_show_id_only = document.getElementById('cb_show_id_only')
    var cb_show_info = document.getElementById('cb_show_info')
    var cb_animation = document.getElementById('cb_animation')
    var btn_station_search = document.getElementById('btn_station_search')

    var bus_stop_list = []
    var bus_stop_auto_complete

    if (lastbus)
        lastbus.onclick = function () {
            get_cds_bus()
        }

    if (cb_show_labels) {
        cb_show_labels.onclick = function () {
            get_bus_stop_list()
        }
    }

    if (cb_show_id_only) {
        cb_show_id_only.onclick = function () {
            get_bus_stop_list()
        }
    }
    if (cb_show_info) {
        cb_show_info.onclick = function () {
            var show = cb_show_info.checked
            businfo.className = show ? "" : "hide_info"
        }
    }

    if (btn_station_search) {
        btn_station_search.onclick = function () {
            run_search_by_name()
        }
    }
    if (lastbusquery) {
        lastbusquery.onkeyup = function (event) {
            event.preventDefault()
            if (event.keyCode === 13) {
                get_cds_bus()
            }
        }
    }

    if (station_query) {
        station_query.onkeyup = function (event) {
            event.preventDefault()
            if (event.keyCode === 13) {
                run_search_by_name()
            }
        }
    }

    function run_timer(func) {
        if (cb_show_labels.checked && !timer_id) {
            timer_id = setTimeout(function tick() {
                func().then(function () {
                    if (cb_show_labels.checked)
                        timer_id = setTimeout(tick, 30 * 1000)
                })
            }, 30 * 1000)
            if (!timer_stop_id)
                timer_stop_id = setTimeout(function () {
                    cb_show_labels.checked = false
                    clearTimeout(timer_id)
                    timer_id = 0
                    timer_stop_id = 0

                }, 10 * 60 * 1000)
        }
    }

    function setCookie(name, value, options) {
        options = options || {};

        var expires = options.expires;

        if (typeof expires === "number" && expires) {
            var d = new Date();
            d.setTime(d.getTime() + expires * 1000);
            expires = options.expires = d;
        }
        if (expires && expires.toUTCString) {
            options.expires = expires.toUTCString();
        }

        value = encodeURIComponent(value);

        var updatedCookie = name + "=" + value;

        for (var propName in options) {
            updatedCookie += "; " + propName;
            var propValue = options[propName];
            if (propValue !== true) {
                updatedCookie += "=" + propValue;
            }
        }

        document.cookie = updatedCookie;
    }

    function getCookie(name) {
        var matches = document.cookie.match(new RegExp(
            "(?:^|; )" + name.replace(/([\.$?*|{}\(\)\[\]\\\/\+^])/g, '\\$1') + "=([^;]*)"
        ));
        return matches ? decodeURIComponent(matches[1]) : undefined;
    }

    function update_user_position() {
        if ("geolocation" in navigator) {
            navigator.geolocation.getCurrentPosition(function (position) {
                coords = position.coords
            })
        }
    }

    if ("geolocation" in navigator) {
        var nextbus = document.getElementById('nextbus')

        if (nextbus)
            nextbus.onclick = function (event) {
                event.preventDefault()
                get_current_pos(get_bus_arrival)
            }
    }

    function save_station_params() {
        var query = station_query.value
        var station = station_name.value

        save_to_ls('station_query', query)
        save_to_ls('station', station)
    }

    function get_current_pos(func) {
        save_station_params()

        navigator.geolocation.getCurrentPosition(func)
    }

    function format_bus_stops(header, bus_stops) {
        var bus_stop_info = header + '\n'
        for (var prop in bus_stops) {
            bus_stop_info += '<a class="bus_linked" href="">' + prop + '</a>' + '\n' + bus_stops[prop] + '\n'
        }

        info.innerHTML = bus_stop_info
        var elements = document.getElementsByClassName('bus_linked')
        for (var i = 0; i < elements.length; i++) {
            elements[i].onclick = function (e) {
                e.preventDefault()
                if (e.srcElement && e.srcElement.text) {
                    station_name.value = e.srcElement.text
                    get_bus_arrival_by_name()
                }
            }
        }
    }

    function waiting(element, button, state) {
        element.className = state ? 'spinner' : ''
        button.disabled = state
    }


    function get_bus_stop_list() {
        var show_labels = cb_show_labels.checked;
        var show_id_only = cb_show_id_only.checked;

        if (bus_stop_list.length > 0) {
            return update_bus_stops(bus_stop_list, show_labels, show_id_only)
        }

        return fetch('/bus_stops',
            {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                },
            })
            .then(function (res) {
                return res.json()
            })
            .then(function (data) {
                update_cookies()
                bus_stop_list = data.result

                update_bus_stops_autocomplete(bus_stop_list, show_labels)
                update_bus_stops(bus_stop_list)
            })
    }

    function update_bus_stops_autocomplete(bus_stop_list) {
        update_cookies()

        if (!station_name) {
            return;
        }

        bus_stop_auto_complete = new autoComplete({
            selector: station_name,
            minChars: 1,
            source: function (term, suggest) {
                term = term.toLowerCase();
                var id = parseInt(term, 10);
                var matches = [];
                for (var i = 0; i < bus_stop_list.length; i++) {
                    var bus_stop = bus_stop_list[i]
                    var name_with_id = bus_stop.ID + " " + bus_stop.NAME_
                    if (Number.isInteger(id)) {
                        if (id === bus_stop.ID) {
                            matches.push(bus_stop);
                        }
                    } else if (~name_with_id.toLowerCase().indexOf(term)) {
                        matches.push(bus_stop);
                    }
                }
                suggest(matches);
            },
            renderItem: function (item, search) {
                search = search.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&');
                var re = new RegExp("(" + search.split(' ').join('|') + ")", "gi");
                var name_with_id = item.ID + " " + item.NAME_
                var data_values = 'data-lat="' + item.LAT_ + '" data-lng="' + item.LON_ + '"'
                return '<div class="autocomplete-suggestion" data-val="' + name_with_id + '" ' + data_values + '> '
                    + name_with_id.replace(re, "<b>$1</b>") + '</div>';
            },
            onSelect: function (e, term, item) {
                var lat = item.getAttribute('data-lat')
                var lng = item.getAttribute('data-lng')
                if (cb_animation.checked)
                    l_map.flyTo([lat, lng], 17)
                else
                    l_map.setView([lat, lng], 17)
            }
        })
    }

    function update_bus_stops(bus_stop_list, show_tooltips_always, show_id_only) {
        marker_group.clearLayers()

        bus_stop_list.forEach(function (item) {
            if (!item.LAT_ || !item.LON_) {
                return
            }

            var tooltip_text = show_id_only ? "" + item.ID : item.ID + " " + item.NAME_;

            L.marker([item.LAT_, item.LON_]).on('click', function (e) {
                var blueIconUrl = 'https://cdn.rawgit.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png'
                var greenIconUrl = 'https://cdn.rawgit.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png'
                var url = this.options.icon.options.iconUrl
                var isBlueIcon = url === "marker-icon.png" || url === blueIconUrl

                var icon = new L.Icon({
                    iconUrl: isBlueIcon ? greenIconUrl : blueIconUrl,
                    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
                    iconSize: [25, 41],
                    iconAnchor: [12, 41],
                    popupAnchor: [1, -34],
                    shadowSize: [41, 41]
                });

                this.setIcon(icon)
            }).addTo(marker_group)
                .bindTooltip(tooltip_text, {permanent: show_tooltips_always});
        })

    }

    function update_cookies() {
        var user_ip = getCookie("user_ip")
        if (user_ip) {
            save_to_ls("user_ip", user_ip)
        }
    }

    function save_to_ls(key, value) {
        if (!ls_test()) {
            return
        }
        localStorage.setItem(key, value)
    }

    function load_from_ls(key) {
        if (!ls_test()) {
            return
        }
        return localStorage.getItem(key)
    }

    function ls_test() {
        var test = 'test'
        if (!'localStorage' in window) {
            return false
        }
        try {
            localStorage.setItem(test, test)
            localStorage.removeItem(test)
            return true
        } catch (e) {
            return false
        }
    }

    function init() {
        var user_ip = getCookie("user_ip")
        var ls_user_ip = load_from_ls('user_ip')
        if (!user_ip && ls_user_ip) {
            setCookie("user_ip", ls_user_ip, {expires: 3600 * 24 * 7})
        }


        if (station_name)
            station_name.value = load_from_ls('station') || ''

        l_map = L.map('mapid', {
            fullscreenControl: {
                pseudoFullscreen: true // if true, fullscreen to page width and height
            }
        }).setView([51.6754966, 39.2088823], 13)
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(l_map)

        marker_group = L.layerGroup().addTo(l_map);

        if (station_name) {
            get_bus_stop_list()
        }
    }

    document.addEventListener("DOMContentLoaded", init);
})()