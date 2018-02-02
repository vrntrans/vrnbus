(function () {
    "use strict";
    const XHR = ("onload" in new XMLHttpRequest()) ? XMLHttpRequest : XDomainRequest;
    var coords = {latitude: 51.6754966, longitude: 39.2088823}

    const lastbusquery = document.getElementById('lastbusquery');
    var my_map
    var BusIconContentLayout
    const info = document.getElementById('info');
    const businfo = document.getElementById('businfo');

    document.getElementById('lastbus').onclick = function () {
        const bus_query = lastbusquery.value
        get_bus_positions(bus_query)
    }


    lastbusquery.onkeyup = function (event) {
        event.preventDefault()
        if (event.keyCode === 13) {
            const bus_query = lastbusquery.value
            save_to_ls('bus_query', bus_query)
            if (my_map) {
                get_bus_codd_positions(bus_query)
            }
            else {
                get_bus_positions(bus_query)
            }
        }
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
        const xhr = new XHR();
        coords = position.coords
        const params = 'lat=' + encodeURIComponent(coords.latitude) + '&lon=' + encodeURIComponent(coords.longitude);
        xhr.open('GET', '/arrival?' + params, true);
        xhr.send()
        xhr.onreadystatechange = function () {
            if (this.readyState !== 4) return;

            if (this.status !== 200) {
                info.innerHTML = 'Ошибка: ' + (this.status ? this.statusText : 'запрос не удался')
                return
            }
            const data = JSON.parse(this.responseText);
            info.innerHTML = data.text
        }
    }

    function get_bus_list() {
        const xhr = new XHR();

        xhr.open('GET', '/buslist', true);
        xhr.send()
        xhr.onreadystatechange = function () {
            if (this.readyState !== 4) return;

            if (this.status !== 200) {
                info.innerHTML = 'Ошибка: ' + (this.status ? this.statusText : 'запрос не удался')
                return
            }
            const data = JSON.parse(this.responseText);
            const bus_list = data.result

            var select = document.getElementById('buslist')

            bus_list.forEach(function (bus_name) {
                var opt = new Option(bus_name, bus_name)
                select.appendChild(opt)
            })

            select.onchange = function (event) {
                var text = select.options[select.selectedIndex].text; // Текстовое значение для выбранного option
                lastbusquery.value += ' ' + text
            }
        }
    }

    function get_bus_positions(query) {
        const xhr = new XHR();

        save_to_ls('bus_query', query)
        var params = 'q=' + encodeURIComponent(query)
        if (coords) {
            params += '&lat=' + encodeURIComponent(coords.latitude)
            params += '&lon=' + encodeURIComponent(coords.longitude)
        }
        xhr.open('GET', '/businfo?' + params, true);
        xhr.send()
        xhr.onreadystatechange = function () {
            if (this.readyState !== 4) return;

            if (this.status !== 200) {
                info.innerHTML = 'Ошибка: ' + (this.status ? this.statusText : 'запрос не удался')
                return
            }
            const data = JSON.parse(this.responseText);
            const q = data.q
            const text = data.text
            businfo.innerHTML = 'Маршруты: ' + q + '\n' + text

            if (!my_map)
                return

            my_map.geoObjects.removeAll()
            const bus_with_azimuth = data.buses.map(function (data) {
                var bus = data[0]
                var next_bus_stop = data[1]
                if (!next_bus_stop.LON_ || !next_bus_stop.LAT_) {
                    return bus
                }

                const x = next_bus_stop.LON_ - bus.last_lat_
                const y = next_bus_stop.LAT_ - bus.last_lon_

                bus.azimuth = Math.floor(Math.atan2(y, x) * 180 / Math.PI)
                return bus
            })
            update_map(bus_with_azimuth, false)
        }
    }

    function get_bus_codd_positions(query) {
        const xhr = new XHR();

        save_to_ls('bus_query', query)
        var params = 'q=' + encodeURIComponent(query)
        if (coords) {
            params += '&lat=' + encodeURIComponent(coords.latitude)
            params += '&lon=' + encodeURIComponent(coords.longitude)
        }
        xhr.open('GET', '/coddbus?' + params, true);
        xhr.send()
        xhr.onreadystatechange = function () {
            if (this.readyState !== 4) return;

            if (this.status !== 200) {
                info.innerHTML = 'Ошибка: ' + (this.status ? this.statusText : 'запрос не удался')
                return
            }
            const data = JSON.parse(this.responseText);
            update_map(data.result)
        }
    }

    function update_map(buses, clear = true) {
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
        const hint = bus.last_time_ + '; ' + bus.azimuth
        const desc = bus.last_time_ + JSON.stringify(bus, null, ' ')

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

    function load_from_ls(key, default_value = '') {
        if (!ls_test()) {
            return default_value
        }
        return localStorage.getItem(key) || default_value
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
        lastbusquery.value = busquery
    }

    document.addEventListener("DOMContentLoaded", init);
})()