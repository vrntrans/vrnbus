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

    lastbus.onclick = function () {
        get_cds_bus()
    }

    cb_refresh.onclick = function () {
        if (!cb_refresh.checked){
            clearTimeout(timer_id)
            clearTimeout(timer_stop_id)
            timer_id = 0
            timer_stop_id = 0
        }
    }

    lastbusquery.onkeyup = function (event) {
        event.preventDefault()
        if (event.keyCode === 13) {
            get_cds_bus()
        }
    }

    function get_cds_bus() {
        if (cb_refresh.checked && !timer_id){
            timer_id = setTimeout(function tick() {
                get_cds_bus().then(function () {
                    timer_id = setTimeout(tick, 30*1000);
                })
            }, 30*1000)
            if (!timer_stop_id)
                timer_stop_id = setTimeout(function () {
                    cb_refresh.checked = false
                    clearTimeout(timer_id)
                    timer_id = 0
                    timer_stop_id = 0

                }, 10*30*1000)
        }

        const bus_query = lastbusquery.value
        save_to_ls('bus_query', bus_query)
        return get_bus_positions(bus_query)
    }

    if ("geolocation" in navigator) {
        const nextbusgeo = document.getElementById('nextbusgeo');
        nextbusgeo.onclick = function (event) {
            event.preventDefault()
            get_current_pos()
        }
    }

    function get_current_pos() {
        navigator.geolocation.getCurrentPosition(get_bus_arrival)
    }

    function get_bus_arrival(position) {
        const nextbusgeo = document.getElementById('nextbusgeo')
        nextbus_loading.className = "spinner"
        nextbusgeo.disabled = true

        coords = position.coords
        const params = 'lat=' + encodeURIComponent(coords.latitude) + '&lon=' + encodeURIComponent(coords.longitude);

        fetch('/arrival?' + params,
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
                nextbus_loading.className = ""
                nextbusgeo.disabled = false
                info.innerHTML = data.text
            })
            .catch(function (error) {
                nextbus_loading.className = ""
                nextbusgeo.disabled = false
                info.innerHTML = 'Ошибка: ' + error
            })
    }

    function waiting(element, button, state){
        element.className = state ? 'spinner': ''
        lastbus.disabled = state
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
                businfo.innerHTML = 'Маршруты: ' + q + '\n' + text

                if (!my_map)
                    return

                const bus_with_azimuth = data.buses.map(function (data) {
                    var bus = data[0]
                    var next_bus_stop = data[1]
                    if (!next_bus_stop.LON_ || !next_bus_stop.LAT_) {
                        return bus
                    }

                    bus.hint = next_bus_stop.NAME_
                    bus.desc = 'Следующая остановка:' + next_bus_stop.NAME_ + ' ' + bus.name_ + ' ' + bus.last_time_

                    const x = next_bus_stop.LON_ - bus.last_lat_
                    const y = next_bus_stop.LAT_ - bus.last_lon_

                    bus.azimuth = Math.floor(Math.atan2(y, x) * 180 / Math.PI)
                    return bus
                })
                update_map(bus_with_azimuth, true)
            }).catch(function (error) {
            waiting(lastbus_loading, lastbus, false)

            businfo.innerHTML = 'Ошибка: ' + error
        })
    }

    function get_bus_list() {
        fetch('/buslist',
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

                select.onchange = function (event) {
                    var text = select.options[select.selectedIndex].text; // Текстовое значение для выбранного option
                    if (text !== '-')
                        lastbusquery.value += ' ' + text
                }
            })
    }

    function get_bus_codd_positions(query) {
        const lastbus_codd = document.getElementById('lastbus_codd')
        lastbus_loading.className = "spinner"
        lastbus_codd.disabled = true
        save_to_ls('bus_query', query)
        var params = 'q=' + encodeURIComponent(query)
        if (coords) {
            params += '&lat=' + encodeURIComponent(coords.latitude)
            params += '&lon=' + encodeURIComponent(coords.longitude)
        }

        fetch('/coddbus?' + params,
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
                lastbus_loading.className = ""
                lastbus_codd.disabled = false

                update_map(data.result, true)
            }).catch(function (error) {
            lastbus_loading.className = ""
            lastbus_codd.disabled = false

            businfo.innerHTML = 'Ошибка: ' + error
        })
    }


    function update_map(buses, clear) {
        if (!my_map) {
            return
        }

        if (clear) {
            my_map.geoObjects.removeAll()
        }
        buses.forEach(function (bus) {
            add_bus(bus)
        })
    }

    function add_bus(bus) {
        if (!bus) {
            return
        }
        const hint = bus.hint ? bus.hint : bus.last_time_ + '; ' + bus.azimuth
        const desc = bus.desc ? bus.desc : bus.last_time_ + JSON.stringify(bus, null, ' ')

        const bus_mark = new BusMark(bus, bus.route_name_.trim(), hint, desc)
        my_map.geoObjects.add(bus_mark)
        return bus_mark
    }

    var BusMark = function (bus, caption, hint, description) {
        const lat = bus.lat2 || bus.last_lat_
        const lon = bus.lon2 || bus.last_lon_
        this.placemark = new ymaps.Placemark([lat, lon], {
            hintContent: hint,
            balloonContent: description,
            iconContent: caption,
            rotation: bus.azimuth,
        }, {
            // Опции.
            // Необходимо указать данный тип макета.
            iconLayout: 'default#imageWithContent',
            // Своё изображение иконки метки.
            iconImageHref: 'bus_round.png',
            // Размеры метки.
            iconImageSize: [32, 32],
            // Смещение левого верхнего угла иконки относительно
            // её "ножки" (точки привязки).
            iconImageOffset: [-16, -16],
            // Смещение слоя с содержимым относительно слоя с картинкой.
            iconContentOffset: [0, 0],
            // Макет содержимого.
            iconContentLayout: BusIconContentLayout,
        });
        return this.placemark
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
            test_mark()
        }
    }


    function test_mark() {
        const bus_obj = {
            "obj_id_": 0,
            "proj_id_": 0,
            "last_speed_": 0,
            "last_lon_": 39.262801,
            "last_lat_": 51.683984,
            "lon2": 0,
            "lat2": 0,
            "azimuth": 0,
            "dist": 0,
            "last_time_": "Jan 31, 2018 11:42:48 AM",
            "route_name_": "18 ",
            "type_proj": 0,
            "lowfloor": 0
        };

        my_map.setCenter([bus_obj.last_lat_, bus_obj.last_lon_])
        my_map.geoObjects.removeAll()

        const bus_mark = add_bus(bus_obj)

        const marker = new ymaps.Placemark([bus_obj.last_lat_, bus_obj.last_lon_], {
            rotation: 0
        }, {});
        my_map.geoObjects.add(marker);
        var i = 0
        // начать повторы с интервалом 2 сек
        const timerId = setInterval(function () {
            const rotation = (5 * (i++));
            bus_mark.properties.set('rotation', rotation);
            bus_mark.properties.set('iconContent', rotation);
            // bus_marker.balloon.open();
        }, 100);

        setTimeout(function () {
            clearInterval(timerId);
        }, 50000);
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