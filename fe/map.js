(function () {
    "use strict";

    if (location.protocol !== 'https:' && location.hostname !== 'localhost') {
        location.href = 'https:' + window.location.href.substring(window.location.protocol.length);
    }

    var coords = {latitude: 51.6754966, longitude: 39.2088823}

    var lastbusquery = document.getElementById('lastbusquery')
    var station_query = document.getElementById('station_query')
    var station_name = document.getElementById('station_name')
    var my_map
    var BusIconContentLayout
    var timer_id = 0
    var timer_stop_id = 0

    var info = document.getElementById('info')
    var businfo = document.getElementById('businfo')
    var lastbus = document.getElementById('lastbus')
    var nextbus_loading = document.getElementById('nextbus_loading')
    var lastbus_loading = document.getElementById('lastbus_loading')
    var cb_refresh = document.getElementById('cb_refresh')
    var cb_show_info = document.getElementById('cb_show_info')
    var btn_station_search = document.getElementById('btn_station_search')

    var bus_stop_list = []
    var bus_stop_names = []
    var bus_stop_auto_complete

    if (lastbus)
        lastbus.onclick = function () {
            get_cds_bus()
        }

    if (cb_refresh)
        cb_refresh.onclick = function () {
            if (!cb_refresh.checked) {
                clearTimeout(timer_id)
                clearTimeout(timer_stop_id)
                timer_id = 0
                timer_stop_id = 0
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

    if (station_name) {
        station_name.onkeyup = function (event) {
            event.preventDefault()
            if (event.keyCode === 13) {
                run_search_by_name()
            }
        }
    }

    function run_timer(func) {
        if (cb_refresh.checked && !timer_id) {
            timer_id = setTimeout(function tick() {
                func().then(function () {
                    if (cb_refresh.checked)
                        timer_id = setTimeout(tick, 30 * 1000)
                })
            }, 30 * 1000)
            if (!timer_stop_id)
                timer_stop_id = setTimeout(function () {
                    cb_refresh.checked = false
                    clearTimeout(timer_id)
                    timer_id = 0
                    timer_stop_id = 0

                }, 10 * 60 * 1000)
        }
    }

    function run_search_by_name() {
        run_timer(run_search_by_name)
        return get_bus_arrival_by_name()
    }

    function get_cds_bus() {
        run_timer(get_cds_bus)

        var bus_query = lastbusquery.value
        save_to_ls('bus_query', bus_query)
        return get_bus_positions(bus_query)
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

    function get_bus_arrival_by_name() {
        var btn_station_search = document.getElementById('btn_station_search')
        waiting(nextbus_loading, btn_station_search, true)

        var bus_query = station_query.value
        var station = station_name.value

        save_station_params()

        var params = 'q=' + encodeURIComponent(bus_query) +
            '&station=' + encodeURIComponent(station)

        return fetch('/bus_stop_search?' + params,
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
                waiting(nextbus_loading, btn_station_search, false)
                format_bus_stops(data.header, data.bus_stops)
            })
            .catch(function (error) {
                waiting(nextbus_loading, btn_station_search, false)
                info.innerHTML = 'Ошибка: ' + error
            })
    }

    function get_bus_arrival(position) {
        var nextbus = document.getElementById('nextbus')
        waiting(nextbus_loading, nextbus, true)

        coords = position.coords
        var bus_query = station_query.value

        var params = 'q=' + encodeURIComponent(bus_query) +
            '&lat=' + encodeURIComponent(coords.latitude) +
            '&lon=' + encodeURIComponent(coords.longitude)

        return fetch('/arrival?' + params,
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
                waiting(nextbus_loading, nextbus, false)
                format_bus_stops(data.header, data.bus_stops)
            })
            .catch(function (error) {
                waiting(nextbus_loading, nextbus, false)
                info.innerHTML = 'Ошибка: ' + error
            })
    }


    function waiting(element, button, state) {
        element.className = state ? 'spinner' : ''
        button.disabled = state
    }

    function get_bus_positions(query) {
        waiting(lastbus_loading, lastbus, true)

        var params = 'q=' + encodeURIComponent(query)
        if (coords) {
            params += '&lat=' + encodeURIComponent(coords.latitude)
            params += '&lon=' + encodeURIComponent(coords.longitude)
        }

        return fetch('/businfo?' + params,
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
                waiting(lastbus_loading, lastbus, false)
                var q = data.q
                var text = data.text
                businfo.innerHTML = 'Маршруты: ' + q + '\nКоличество результатов: ' + data.buses.length + '\n' + text

                if (!my_map)
                    return

                var bus_with_azimuth = data.buses.map(function (data) {
                    var bus = data[0]
                    var next_bus_stop = data[1]
                    if (!next_bus_stop.LON_ || !next_bus_stop.LAT_) {
                        return bus
                    }

                    bus.hint = next_bus_stop.NAME_

                    var x = next_bus_stop.LAT_ - bus.last_lat_
                    var y = next_bus_stop.LON_ - bus.last_lon_

                    bus.azimuth = Math.floor(Math.atan2(y, x) * 180 / Math.PI)
                    var time = bus.last_time_.substring(bus.last_time_.length - 8)

                    bus.desc = [time + " " + next_bus_stop.NAME_,
                        bus.route_name_.trim() + " ( " + bus.name_ + " ) ",
                        bus.last_lat_ + " " + bus.last_lon_].join('<br/>')

                    return bus
                })
                update_map(bus_with_azimuth, true)
            }).catch(function (error) {
                waiting(lastbus_loading, lastbus, false)

                businfo.innerHTML = 'Ошибка: ' + error
            })
    }

    function get_bus_stop_list() {
        return fetch('/bus_stops.json',
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
                bus_stop_list = data
                bus_stop_names = bus_stop_list.map(function callback(bus_stop) {
                    return bus_stop.NAME_
                })
                bus_stop_auto_complete = new autoComplete({
                    selector: station_name,
                    source: function (term, suggest) {
                        term = term.toLowerCase();
                        var matches = [];
                        for (var i = 0; i < bus_stop_names.length; i++)
                            if (~bus_stop_names[i].toLowerCase().indexOf(term)) matches.push(bus_stop_names[i]);
                        suggest(matches);
                    }
                })

            })
    }


    function get_bus_list() {
        return fetch('/buslist',
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
                var bus_list = data.result

                var select = document.getElementById('buslist')
                select.appendChild(new Option('Маршруты', '-'))
                bus_list.forEach(function (bus_name) {
                    var opt = new Option(bus_name, bus_name)
                    select.appendChild(opt)
                })

                select.onchange = function () {
                    var text = select.options[select.selectedIndex].text; // Текстовое значение для выбранного option
                    if (text !== '-') {
                        if (lastbusquery)
                            lastbusquery.value += ' ' + text
                        if (station_query)
                            station_query.value += ' ' + text
                    }
                }
            })
    }

    function update_map(buses, clear) {
        if (!my_map) {
            return
        }

        var objectManager = new ymaps.ObjectManager()

        objectManager.objects.options.set({
            iconLayout: 'default#imageWithContent',
            iconImageHref: 'bus_round.png',
            iconImageSize: [32, 32],
            iconImageOffset: [-16, -16],
            iconContentOffset: [0, 0],
            iconContentLayout: BusIconContentLayout,
        })

        var features = []

        buses.forEach(function (bus, index) {
            features.push(add_bus(bus, index))
        })

        objectManager.add({
            "type": "FeatureCollection",
            "features": features
        })

        if (clear) {
            my_map.geoObjects.removeAll()
        }

        my_map.geoObjects.add(objectManager)
    }

    function add_bus(bus, id) {
        if (!bus) {
            return
        }
        var hint_content = bus.hint ? bus.hint : bus.last_time_ + '; ' + bus.azimuth
        var balloon_content = bus.desc ? bus.desc : bus.last_time_ + JSON.stringify(bus, null, ' ')
        var lat = bus.lat2 || bus.last_lat_
        var lon = bus.lon2 || bus.last_lon_
        var icon_content = bus.route_name_.trim()
        var rotation = bus.azimuth

        return {
            "type": "Feature",
            "id": id,
            "geometry": {"type": "Point", "coordinates": [lat, lon]},
            "properties": {
                "balloonContent": balloon_content,
                "hintContent": hint_content,
                "iconContent": icon_content,
                "rotation": rotation,
                "clusterCaption": icon_content + ' ' + hint_content
            }
        }
    }

    if ('ymaps' in window) {
        ymaps.ready(ymap_show);
    }

    function ymap_show() {
        my_map = new ymaps.Map('map', {
            center: [coords.latitude, coords.longitude],
            zoom: 14
        }, {
            searchControlProvider: 'yandex#search'
        })

        BusIconContentLayout = ymaps.templateLayoutFactory.createClass(
            '<img class="bus-icon" style=" z-index: -1; transform: rotate({{properties.rotation}}deg);" src="arrow.png">' +
            '<ymaps class="bus-title" style="z-index: -2;"> $[properties.iconContent] </ymaps>'
        )

        if (location.hostname === "localhost" || location.hostname === "127.0.0.1") {
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
        get_bus_list()
        get_bus_stop_list()

        if (lastbusquery)
            lastbusquery.value = load_from_ls('bus_query') || ''

        if (station_query)
            station_query.value = load_from_ls('station_query') || ''

        if (station_name)
            station_name.value = load_from_ls('station') || ''
    }

    document.addEventListener("DOMContentLoaded", init);
})()