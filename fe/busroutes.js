(function () {
    "use strict";
    var map;
    var marker_group;
    var my_renderer;
    var coords = {latitude: 51.6754966, longitude: 39.2088823}

    var bus_route_stops = []
    var bus_stop_auto_complete
    var drawn_items


    function get_bus_stops_routes() {
        if (bus_route_stops.length > 0) {
            return update_bus_stops_routes(bus_route_stops)
        }

        return fetch('/bus_stops_routes',
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
                bus_route_stops = data
                // update_bus_stops_routes(data)
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
                var bus_list = data.result

                var select = document.getElementById('bus_routes')
                select.appendChild(new Option('Все маршруты', ''))
                bus_list.forEach(function (bus_name) {
                    var opt = new Option(bus_name, bus_name)
                    select.appendChild(opt)
                })

                select.onchange = function () {
                    var route_name = select.options[select.selectedIndex].value;
                    if (route_name || document.getElementById('show_all_routes').checked){
                        update_bus_stops_routes(bus_route_stops, route_name)
                    }
                }

                document.getElementById('busnumber').onchange = select.onchange;
                document.getElementById('busspeed').onchange = select.onchange;
                document.getElementById('show_all_routes').onchange = select.onchange;
                document.getElementById('wait_time').onchange = select.onchange;
            })
    }


    function update_bus_stops_routes(bus_stops_routes, selected_route_name) {
        drawn_items.clearLayers()
        marker_group.clearLayers()
        var my_renderer = L.canvas({padding: 0.5});
        var edges = {}
        var bus_stops = {}
        var wrong_stops = []
        var route_by_edges = {}

        var natural_collator = new Intl.Collator(undefined, {numeric: true, sensitivity: 'base'});



        for (var route_name in bus_stops_routes) {
            if (!route_name)
                continue
            if (selected_route_name && route_name !== selected_route_name)
                continue
            var route = bus_stops_routes[route_name]
            var curr_point = route[0]
            route.forEach(function (item) {
                if (curr_point === item) {
                    return
                }

                var edge_key = [curr_point.ID, item.ID]
                var edge_info = `( ${edge_key} ) ${curr_point.NAME_} - ${item.NAME_}`
                if (!(edge_key in route_by_edges)){
                    route_by_edges[edge_key] = []
                }

                route_by_edges[edge_key].push(route_name)
                route_by_edges[edge_key].sort(natural_collator.compare)

                var edge = edges[edge_key]
                var routes = route_by_edges[edge_key]
                var popup_content = `${edge_info}<br/>` +  routes.join('<br/>')

                if (edge_key in edges) {
                    edge.setPopupContent(popup_content)
                    curr_point = item
                    return
                }

                if (curr_point.NUMBER_ === item.NUMBER_) {
                    console.log(edge_info)
                }

                var pointA = new L.LatLng(curr_point.LAT_, curr_point.LON_);
                var pointB = new L.LatLng(item.LAT_, item.LON_);
                var pointList = [pointA, pointB];

                var firstpolyline = new L.Polyline(pointList, {
                    color: 'blue',
                    weight: 5,
                    opacity: 0.5,
                    smoothFactor: 1,
                    edge_key: edge_key,
                    edge_info: edge_info
                }).bindPopup(popup_content);
                // firstpolyline.addTo(map);
                drawn_items.addLayer(firstpolyline)

                edges[edge_key] = firstpolyline

                curr_point = item

            })
        }

        if (selected_route_name) {
            var length_route = 0;
            var previousPoint = null;
            Object.values(edges).forEach((polyline) => {
                polyline.getLatLngs().forEach(function (latLng) {
                    if (previousPoint) {
                        length_route += previousPoint.distanceTo(latLng)/1000
                    }
                    previousPoint = latLng;
                });
            })
            var routeinfo = document.getElementById('routeinfo');
            var busnumber = document.getElementById('busnumber').value;
            var busspeed = document.getElementById('busspeed').value;
            var wait_time = document.getElementById('wait_time').value;
            var minute_interval = ((length_route + (wait_time/60)*busspeed)/busnumber)*60/busspeed;
            routeinfo.innerText = `${selected_route_name} - ${length_route.toFixed(2)} км, ${busnumber}, ${minute_interval.toFixed(2)} минут `
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
        map = L.map('mapid', {
            fullscreenControl: {
                pseudoFullscreen: true // if true, fullscreen to page width and height
            }
        }).setView([51.6754966, 39.2088823], 11)

        my_renderer = L.canvas({padding: 0.5});

        L.tileLayer('https://maps.wikimedia.org/osm-intl/{z}/{x}/{y}.png', {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        }).addTo(map)

        // FeatureGroup is to store editable layers
        drawn_items = new L.FeatureGroup();
        map.addLayer(drawn_items);

        map.addControl(new L.Control.Draw({
            edit: {
                featureGroup: drawn_items,
                poly: {
                    allowIntersection: false
                }
            },
            draw: {
                polygon: {
                    allowIntersection: false,
                    showArea: true
                }
            }
        }));


        map.on("draw:created", function (event) {
            var layer = event.layer;

            // drawn_items.addLayer(layer);
        });

        map.on('draw:edited', function (e) {
            var layers = e.layers;
            layers.eachLayer(function (layer) {
                console.log(layer)
            });
        });

        marker_group = L.layerGroup().addTo(map);
        L.control.ruler().addTo(map);

        get_bus_list()
        get_bus_stops_routes()
    }

    document.addEventListener("DOMContentLoaded", init);
})()