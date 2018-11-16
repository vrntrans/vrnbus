(function () {
    "use strict";

    if (location.protocol !== 'https:' && location.hostname !== 'localhost') {
        location.href = 'https:' + window.location.href.substring(window.location.protocol.length);
    }

    var l_map;
    var marker_group;
    var my_renderer;
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
    var cb_show_png_markers = document.getElementById('cb_show_png_markers')
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

    if (cb_show_png_markers) {
        cb_show_png_markers.onclick = function () {
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
        var show_png_markers = cb_show_png_markers.checked;

        if (bus_stop_list.length > 0) {
            return update_bus_stops(bus_stop_list, show_labels, show_id_only, show_png_markers)
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
                    if (Number.isInteger(id) && id.toString(10) === term) {
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

    function add_circle_marker(item) {
        var marker_colors = ["#3388ff",
            "#330088",
            "#ff662e"]

        return L.circleMarker([item.LAT_, item.LON_], {
            renderer: my_renderer,
            fill: true,
            fillOpacity: 0.9,
            color: "#3388ff"
        }).on('click', function (e) {

            var color_index = marker_colors.indexOf(e.target.options.color) + 1
            if (color_index >= marker_colors.length) {
                color_index = 0
            }

            e.target.setStyle({
                color: marker_colors[color_index]
            })
        });
    }

    var icon_urls = []

    function add_png_marker(item) {
        var shadowUrl = 'https://unpkg.com/leaflet@1.3.3/dist/images/marker-shadow.png'

        var icon = new L.Icon({
            iconUrl: icon_urls[0],
            shadowUrl: shadowUrl,
            iconSize: [25, 41],
            iconAnchor: [12, 41],
            popupAnchor: [1, -34],
            shadowSize: [41, 41]
        });

        return L.marker([item.LAT_, item.LON_],
            {
                icon: icon
            }
        ).on('click', function (e) {

            var icon_index = icon_urls.indexOf(e.target.options.icon.options.iconUrl) + 1
            if (icon_index >= icon_urls.length) {
                icon_index = 0
            }

            var icon = new L.Icon({
                iconUrl: icon_urls[icon_index],
                shadowUrl: shadowUrl,
                iconSize: [25, 41],
                iconAnchor: [12, 41],
                popupAnchor: [1, -34],
                shadowSize: [41, 41]
            });

            this.setIcon(icon)
        })
    }


    function update_bus_stops(bus_stop_list, show_tooltips_always, show_id_only, show_png_markers) {
        marker_group.clearLayers()
        var wrong_stops = []

        bus_stop_list.forEach(function (item) {
            if (!item.LAT_ || !item.LON_ || item.LON_ < 30 || item.LAT_ < 30) {
                wrong_stops.push(item);
                return
            }

            var tooltip_text = show_id_only ? "" + item.ID : item.ID + " " + item.NAME_;
            var marker = show_png_markers ? add_png_marker(item) : add_circle_marker(item)

            marker
                .addTo(marker_group)
                .bindTooltip(tooltip_text, {permanent: show_tooltips_always})
        })

        var wrong_stops_info = "Проверьте координаты остановок:<br/>"
        wrong_stops.forEach(function (item) {
            wrong_stops_info += item.ID + " " + item.NAME_ + " (" + item.LAT_ + ", " + item.LON_ + ") " + "<br/>"
        })
        businfo.innerHTML = wrong_stops_info
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

        my_renderer = L.canvas({padding: 0.5});

        L.tileLayer('https://maps.wikimedia.org/osm-intl/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(l_map)

        marker_group = L.layerGroup().addTo(l_map);

        // var myIcon = L.divIcon({className: '',
        //     html: '<img class="bus-icon" style=" z-index: -1; transform: rotate(120deg);" src="arrow.png">' +
        //         '<img class="bus-icon" style=" z-index: 1;" src="bus_round.png">' +
        //         '<div class="bus-title" style="z-index: -2;"> HELLO </div>'
        // });
        // // you can set .my-div-icon styles in CSS
        // L.marker([51.6754966, 39.2088823], {icon: myIcon}).addTo(l_map);

        var iconUrls = [
            'marker-icon-2x-blue.png',
            'marker-icon-2x-green.png',
            'marker-icon-2x-red.png',
        ]

        var base_color_marker_url = 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/'
        iconUrls.forEach(function (value) {
            icon_urls.push(base_color_marker_url + value)
        })

        if (station_name) {
            get_bus_stop_list()
        }
    }

    document.addEventListener("DOMContentLoaded", init);
})()