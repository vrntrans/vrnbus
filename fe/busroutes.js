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
            return update_bus_stops(bus_route_stops, show_labels, show_id_only, show_png_markers)
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
                bus_route_stops = data.result
                update_bus_stops_routes(bus_route_stops)
            })
    }

    function update_bus_stops_routes(bus_stops_routes) {
        drawn_items.clearLayers()
        marker_group.clearLayers()
        var edges = {}
        var wrong_stops = []

        for (var route_name in bus_stops_routes) {
            if (!route_name)
                continue
            var route = bus_stops_routes[route_name]
            var curr_point = route[0]
            route.forEach(function (item) {
                if (curr_point == item) {
                    return
                }
                var edge_key = [curr_point.ID, item.ID]
                if (edge_key in edges) {
                    console.log(edge_key)
                    return
                }

                var pointA = new L.LatLng(curr_point.LAT_, curr_point.LON_);
                var pointB = new L.LatLng(item.LAT_, item.LON_);
                var pointList = [pointA, pointB];

                var firstpolyline = new L.Polyline(pointList, {
                    color: 'red',
                    weight: 3,
                    opacity: 0.5,
                    smoothFactor: 1
                }).bindPopup(`${route_name} ( ${edge_key} ) ${curr_point.NAME_} - ${item.NAME_}`);
                // firstpolyline.addTo(map);
                drawn_items.addLayer(firstpolyline)

                edges[edge_key] = firstpolyline

                curr_point = item

            })
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


        map.on("draw:created draw:edited", function (event) {
            var layer = event.layer;

            // drawn_items.addLayer(layer);
        });

        marker_group = L.layerGroup().addTo(map);


        get_bus_stops_routes()
    }

    document.addEventListener("DOMContentLoaded", init);
})()