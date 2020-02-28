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
    var lastbus_map_update = document.getElementById('lastbus_map_update')
    var nextbus_loading = document.getElementById('nextbus_loading')
    var lastbus_loading = document.getElementById('lastbus_loading')
    var cb_refresh = document.getElementById('cb_refresh')
    var cb_show_info = document.getElementById('cb_show_info')
    var btn_station_search = document.getElementById('btn_station_search')

    var bus_stop_list = []
    var bus_stop_names = []
    var bus_stop_auto_complete

    if (lastbus_map_update)
        lastbus_map_update.onclick = function () {
            update_bus_map()
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
                update_bus_map()
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

    function set_query_parameter(name, value) {
        const params = new URLSearchParams(window.location.search);
        params.set(name, value);
        window.history.replaceState({}, "", decodeURIComponent(`${window.location.pathname}?${params}`));
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

                }, 20 * 60 * 1000)
        }
    }

    function run_search_by_name() {
        run_timer(run_search_by_name)

        update_user_position()
        return get_bus_arrival_by_name()
    }

    function update_bus_map() {
        run_timer(update_bus_map)

        var bus_query = lastbusquery.value
        save_to_ls('bus_query', bus_query)
        update_user_position()
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

    function update_user_position() {
        if ("geolocation" in navigator) {
            navigator.geolocation.getCurrentPosition(function (position) {
                coords = position.coords
            })
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

        update_user_position()
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
                credentials: 'include',
            })
            .then(function (res) {
                return res.json()
            })
            .then(function (data) {
                update_cookies()
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
                credentials: 'include',
            })
            .then(function (res) {
                return res.json()
            })
            .then(function (data) {
                update_cookies()
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

    function fraud_check() {
        if (parent !== window) {
            return "&parentUrl=" + encodeURIComponent(document.referrer)
        }
        return ""
    }

    function diff_time(last_time, max_time) {
        var date_1 = new Date(last_time)
        var date_2 = new Date(max_time)

        return (date_2 - date_1)/1000;
    }

    function formate_date(last_time) {
        function pad_zero(number) {
            return ('0' + number).slice(-2)
        }

        var date = new Date(last_time)
        var time = last_time.substring(last_time.length - 8)
        if (Date.now() - date > (3600 * 1000 * 24)) {
            time = date.getFullYear() + '-' + pad_zero(date.getMonth() + 1) + '-' + pad_zero(date.getDate()) + ' ' + time
        }

        return time
    }

    function get_bus_positions(query) {
        waiting(lastbus_loading, lastbus_map_update, true)
        set_query_parameter('bus_query', query)
        var params = 'src=map&q=' + encodeURIComponent(query) + fraud_check()
        if (coords) {
            params += '&lat=' + encodeURIComponent(coords.latitude)
            params += '&lon=' + encodeURIComponent(coords.longitude)
        }

        return fetch('/busmap?' + params,
            {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'include',
            })
            .then(function (res) {
                return res.json()
            })
            .then(function (data) {
                update_cookies()
                waiting(lastbus_loading, lastbus_map_update, false)
                var q = data.q
                var text = data.text
                var server_time = new Date(data.server_time)
                businfo.innerHTML = 'Маршруты: ' + q + '\nКоличество результатов: ' + data.buses.length + '\n' + text

                if (!my_map)
                    return

                if (data.buses.length > 0) {
                    var min_last_time = data.buses[0][0].last_time_;
                    var max_time = data.buses.reduce(function (accumulator, currentValue) {
                        if (currentValue[0].last_time_ > accumulator)
                            return currentValue[0].last_time_;
                        return accumulator;
                    }, min_last_time);

                    var delta_with_current = (new Date() - new Date(max_time))/1000
                    var delta_with_max = (server_time - new Date(max_time))/1000
                    console.log("current_time - max_time", delta_with_current.toFixed(1))
                    console.log("server_time - max_time", delta_with_max.toFixed(1))
                }

                var bus_with_azimuth = data.buses.map(function (data) {
                    var bus = data[0]
                    var next_bus_stop = data[1]
                    if (!next_bus_stop.LON_ || !next_bus_stop.LAT_) {
                        return bus
                    }

                    bus.hint = next_bus_stop.NAME_

                    var x = next_bus_stop.LAT_ - bus.last_lat_
                    var y = next_bus_stop.LON_ - bus.last_lon_

                    bus.db_azimuth = bus.azimuth
                    bus.azimuth = Math.floor(Math.atan2(y, x) * 180 / Math.PI)
                    var time = formate_date(bus.last_time_)
                    var bus_type = "МВ"
                    switch (bus.bus_type) {
                        case 3:
                            bus_type = "СВ"
                            break
                        case 4:
                            bus_type = "БВ"
                            break
                    }
                    var bus_output = bus.obj_output === 1 ? ' <b>!</b> ' : ''

                    bus.delta_time = diff_time(bus.last_time_, server_time);
                    var bus_name = bus.name_ ? bus.name_ : bus.hidden_name;
                    var route_name = bus.route_name_.trim();
                    var fb_link_info = " <a target='_blank' rel='noopener' href='/fotobus_info?name=" + bus_name + "'>" + route_name + " " +  bus.name_ + "</a>";

                    bus.desc = [bus_output + time + " " + next_bus_stop.NAME_,
                        bus.name_ ? fb_link_info : route_name,
                        bus.last_speed_.toFixed(1)
                        + " ~ " + bus.avg_speed.toFixed(1)
                        + " ~ " + bus.avg_last_speed.toFixed(1) + ' км/ч',
                        "Азимуты: к остановке " + bus.azimuth + ';  ' + bus.db_azimuth,
                        (bus.low_floor ? "Низкопол" : "") + " " + bus_type].join('<br/>')

                    return bus
                })
                update_map(bus_with_azimuth, true)
            }).catch(function (error) {
                waiting(lastbus_loading, lastbus_map_update, false)
                console.error(error)
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
                credentials: 'include',
            })
            .then(function (res) {
                return res.json()
            })
            .then(function (data) {
                update_cookies()
                bus_stop_list = data
                bus_stop_names = bus_stop_list.map(function callback(bus_stop) {
                    return bus_stop.NAME_
                })
                if (station_name) {
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
                }

            })
    }


    function get_bus_list() {
        return fetch('/buslist',
            {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                },
                credentials: 'include',
            })
            .then(function (res) {
                return res.json()
            })
            .then(function (data) {
                update_cookies()
                var bus_list = data.result

                var select = document.getElementById('buslist')
                select.appendChild(new Option('Маршруты', '-'))
                bus_list.forEach(function (bus_name) {
                    var opt = new Option(bus_name, bus_name)
                    select.appendChild(opt)
                })

                select.onchange = function () {
                    var text = select.options[select.selectedIndex].value; // Текстовое значение для выбранного option
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
            iconImageHref: 'bus_round_copy.png',
            iconImageSize: [32, 32],
            iconImageOffset: [-16, -16],
            iconContentOffset: [0, 0],
            iconContentLayout: BusIconContentLayout,
            balloonMaxWidth: 250,
        })

        var features = []


        if (clear) {
            my_map.geoObjects.removeAll()
        }


        buses.forEach(function (bus, index) {
            features.push(add_bus(bus, index))
        })

        objectManager.add({
            "type": "FeatureCollection",
            "features": features
        })

        my_map.geoObjects.add(objectManager)
    }

    function add_stop(stop, id) {
        if (!stop) {
            return
        }
        var hint_content = stop.NAME_
        var balloon_content = stop.NAME_
        var lat = stop.LAT_
        var lon = stop.LON_

        return {
            "type": "Feature",
            "id": id,
            "geometry": {"type": "Point", "coordinates": [lat, lon]},
            "properties": {
                "balloonContent": balloon_content,
                "hintContent": hint_content,
                "clusterCaption": hint_content
            }
        }
    }


    function add_bus(bus, id, max_time) {
        if (!bus) {
            return
        }
        var hint_content = bus.hint ? bus.hint : bus.last_time_ + '; ' + bus.azimuth
        var balloon_content = bus.desc ? bus.desc : bus.last_time_ + JSON.stringify(bus, null, ' ')
        var lat = bus.lat2 || bus.last_lat_
        var lon = bus.lon2 || bus.last_lon_
        var bus_output = bus.obj_output === 1 ? ' <b>!</b>' : ''
        var icon_content = bus_output + "&nbsp;" + bus.route_name_.trim() + (bus.name_ ? "&nbsp;" + bus.name_ : "")
        var rotation = bus.db_azimuth
        var wait = bus.delta_time < 60 ? '' : '_wait';
        if (bus.delta_time > 180){
            wait = '_long_wait'
        }
        var file_name = bus.low_floor === 1 ? 'bus_round_lf' : 'bus_round';

        return {
            "type": "Feature",
            "id": id,
            "geometry": {"type": "Point", "coordinates": [lat, lon]},
            "properties": {
                "balloonContent": balloon_content,
                "hintContent": hint_content,
                "iconContent": icon_content,
                "rotation": rotation,
                "clusterCaption": icon_content + ' ' + hint_content,
                'iconImageHref': file_name + wait +'.png',
            },
            "options": {
                iconImageHref:  "img/" + file_name + wait +'.png',
            }
        }
    }

    if ('ymaps' in window) {
        ymaps.ready(ymap_show);
    }

    function add_bus_stops(stops) {
        var objectManager = new ymaps.ObjectManager({
            clusterize: true,
            gridSize: 80,
            clusterDisableClickZoom: true
        })

        objectManager.objects.options.set({
            preset: 'islands#darkGreenCircleDotIcon'
        })

        var features = []

        stops.forEach(function (stop, index) {
            features.push(add_stop(stop, index))
        })

        objectManager.add({
            "type": "FeatureCollection",
            "features": features
        })

        my_map.events.add('click', function (e) {
            my_map.balloon.open(e.get('coords'), 'Щелк!');
            e.stopPropagation()
            e.preventDefault();
        });
        my_map.geoObjects.add(objectManager)
    }

    function ymap_show() {
        var map_zoom = load_from_ls('map_zoom') || 13
        var map_lat = load_from_ls('map_lat') || coords.latitude
        var map_lon = load_from_ls('map_lon') || coords.longitude

        my_map = new ymaps.Map('map', {
            center: [map_lat, map_lon],
            zoom: map_zoom
        }, {
            searchControlProvider: 'yandex#search',
            minZoom: 10,
            maxZoom: 19
        })

        my_map.events.add('boundschange', function (event) {
            save_to_ls('map_zoom', event.get('newZoom'))
            var center = event.get('newCenter')

            save_to_ls('map_lat', center[0])
            save_to_ls('map_lon', center[1])
        });

        BusIconContentLayout = ymaps.templateLayoutFactory.createClass(
            '<img class="bus-icon" style="z-index: -1;transform: rotate({{properties.rotation}}deg);" src="arrow.png"/>' +
            '<ymaps class="bus-title" style="opacity:${{properties.iconOpacity}};z-index: -3;"> $[properties.iconContent] </ymaps>'
        )

        // TODO: Check with buses
        // add_bus_stops(bus_stop_list)
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

    function setCookie(name, value, options) {
        options = options || {};

        var expires = options.expires;

        if (typeof expires == "number" && expires) {
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


    function update_cookies() {
        var user_ip = getCookie("user_ip")
        if (user_ip) {
            save_to_ls("user_ip", user_ip)
        }

        var ls_user_ip = load_from_ls('user_ip')
        if (!user_ip && ls_user_ip) {
            setCookie("user_ip", ls_user_ip, {expires: 3600 * 24 * 7})
        }
    }


    function init() {
        update_cookies()
        if (station_name) {
            get_bus_stop_list()
        }
        get_bus_list()

        firebase.analytics().setUserId(load_from_ls('user_ip') || '');

        const params = new URLSearchParams(window.location.search);
        const bus_query = params.get('bus_query')

        if (lastbusquery)
            lastbusquery.value = load_from_ls('bus_query') || params.get('bus_query') || ''

        if (station_query)
            station_query.value = load_from_ls('station_query') || ''

        if (station_name)
            station_name.value = load_from_ls('station') || ''

        firebase.analytics().logEvent("open_map", {
            user_ip: load_from_ls('user_ip'),
            bus_query: load_from_ls('bus_query'),
        })


    }

    document.addEventListener("DOMContentLoaded", init);
})()