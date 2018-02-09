(function () {
    "use strict";
    var coords = {latitude: 51.6754966, longitude: 39.2088823}

    const lastbusquery = document.getElementById('lastbusquery');
    var my_map
    var BusIconContentLayout
    var timer_id = 0
    var timer_stop_id = 0

    const info = document.getElementById('info')
    const businfo = document.getElementById('businfo')
    const lastbus = document.getElementById('lastbus')
    const nextbus_loading = document.getElementById('nextbus_loading')
    const lastbus_loading = document.getElementById('lastbus_loading')
    const cb_refresh = document.getElementById('cb_refresh')
    const cb_show_info = document.getElementById('cb_show_info')

    lastbus.onclick = function () {
        get_cds_bus()
    }

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
            const show = cb_show_info.checked
            businfo.className = show ? "" : "hide_info"
        }
    }

    lastbusquery.onkeyup = function (event) {
        event.preventDefault()
        if (event.keyCode === 13) {
            get_cds_bus()
        }
    }

    function get_cds_bus() {
        if (cb_refresh.checked && !timer_id) {
            timer_id = setTimeout(function tick() {
                get_cds_bus().then(function () {
                    timer_id = setTimeout(tick, 20 * 1000);
                })
            }, 20 * 1000)
            if (!timer_stop_id)
                timer_stop_id = setTimeout(function () {
                    cb_refresh.checked = false
                    clearTimeout(timer_id)
                    timer_id = 0
                    timer_stop_id = 0

                }, 10 * 30 * 1000)
        }

        const bus_query = lastbusquery.value
        save_to_ls('bus_query', bus_query)
        return get_bus_positions(bus_query)
    }

    if ("geolocation" in navigator) {
        const nextbusgeo = document.getElementById('nextbusgeo');
        const nextbusgeo_alt = document.getElementById('nextbusgeo_alt');
        nextbusgeo.onclick = function (event) {
            event.preventDefault()
            get_current_pos(get_bus_arrival)
        }
        nextbusgeo_alt.onclick = function (event) {
            event.preventDefault()
            get_current_pos(get_bus_arrival_alt)
        }
    }

    function get_current_pos(func) {
        const bus_query = lastbusquery.value
        save_to_ls('bus_query', bus_query)
        navigator.geolocation.getCurrentPosition(func)
    }

    function get_bus_arrival(position) {
        const nextbusgeo = document.getElementById('nextbusgeo')
        waiting(nextbus_loading, nextbusgeo, true)

        const bus_query = lastbusquery.value

        coords = position.coords
        const params = 'q=' + encodeURIComponent(bus_query) + '&lat=' + encodeURIComponent(coords.latitude) + '&lon=' + encodeURIComponent(coords.longitude);

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
                waiting(nextbus_loading, nextbusgeo, false)
                info.innerHTML = data.text
            })
            .catch(function (error) {
                waiting(nextbus_loading, nextbusgeo, false)
                info.innerHTML = 'Ошибка: ' + error
            })
    }

    function get_bus_arrival_alt(position) {
        const nextbusgeo_alt = document.getElementById('nextbusgeo_alt')
        waiting(nextbus_loading, nextbusgeo_alt, true)

        coords = position.coords
        const bus_query = lastbusquery.value

        const params = 'q=' + encodeURIComponent(bus_query) +
            '&lat=' + encodeURIComponent(coords.latitude) +
            '&lon=' + encodeURIComponent(coords.longitude)

        return fetch('/arrival_alt?' + params,
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
                waiting(nextbus_loading, nextbusgeo_alt, false)
                info.innerHTML = data.text
            })
            .catch(function (error) {
                waiting(nextbus_loading, nextbusgeo_alt, false)
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
                const q = data.q
                const text = data.text
                businfo.innerHTML = 'Маршруты: ' + q + '\nКоличество результатов: ' + data.buses.length + '\n' + text

                if (!my_map)
                    return

                const bus_with_azimuth = data.buses.map(function (data) {
                    var bus = data[0]
                    var next_bus_stop = data[1]
                    if (!next_bus_stop.LON_ || !next_bus_stop.LAT_) {
                        return bus
                    }

                    bus.hint = next_bus_stop.NAME_

                    const x = next_bus_stop.LAT_ - bus.last_lat_
                    const y = next_bus_stop.LON_ - bus.last_lon_

                    bus.azimuth = Math.floor(Math.atan2(y, x) * 180 / Math.PI)
                    const time = bus.last_time_.substring(bus.last_time_.length - 8)
                    bus.desc = 'След.: ' + next_bus_stop.NAME_ + ' ' + time + ' ' + bus.name_ + '\nПред: ' + bus.bus_station_

                    return bus
                })
                update_map(bus_with_azimuth, true)
            }).catch(function (error) {
                waiting(lastbus_loading, lastbus, false)

                businfo.innerHTML = 'Ошибка: ' + error
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
                const bus_list = data.result

                var select = document.getElementById('buslist')
                select.appendChild(new Option('-', '-'))
                bus_list.forEach(function (bus_name) {
                    var opt = new Option(bus_name, bus_name)
                    select.appendChild(opt)
                })

                select.onchange = function () {
                    var text = select.options[select.selectedIndex].text; // Текстовое значение для выбранного option
                    if (text !== '-')
                        lastbusquery.value += ' ' + text
                }
            })
    }

    function get_bus_codd_positions(query) {
        const lastbus_codd = document.getElementById('lastbus_codd')
        waiting(lastbus_loading, lastbus_codd, true)
        save_to_ls('bus_query', query)
        var params = 'q=' + encodeURIComponent(query)
        if (coords) {
            params += '&lat=' + encodeURIComponent(coords.latitude)
            params += '&lon=' + encodeURIComponent(coords.longitude)
        }

        return fetch('/coddbus?' + params,
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
                waiting(lastbus_loading, lastbus_codd, false)

                update_map(data.result, true)
            }).catch(function (error) {
                waiting(lastbus_loading, lastbus_codd, false)

                businfo.innerHTML = 'Ошибка: ' + error
            })
    }

    function update_map(buses, clear) {
        if (!my_map) {
            return
        }

        const objectManager = new ymaps.ObjectManager()

        objectManager.objects.options.set({
            iconLayout: 'default#imageWithContent',
            iconImageHref: 'bus_round.png',
            iconImageSize: [32, 32],
            iconImageOffset: [-16, -16],
            iconContentOffset: [0, 0],
            iconContentLayout: BusIconContentLayout,
        })

        const features = []

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
        const hint_content = bus.hint ? bus.hint : bus.last_time_ + '; ' + bus.azimuth
        const balloon_content = bus.desc ? bus.desc : bus.last_time_ + JSON.stringify(bus, null, ' ')
        const lat = bus.lat2 || bus.last_lat_
        const lon = bus.lon2 || bus.last_lon_
        const icon_content = bus.route_name_.trim()
        const rotation = bus.azimuth

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
        document.getElementById('lastbus_codd').onclick = function () {
            const bus_query = lastbusquery.value
            get_bus_codd_positions(bus_query)
        }

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
        const busquery = load_from_ls('bus_query')
        lastbusquery.value = busquery || ''
    }

    document.addEventListener("DOMContentLoaded", init);
})()