Ext.define('CWM.controller.Main', {
    extend: 'Ext.app.Controller',
    views: ['CWM.view.Main', 'CWM.view.BusesInfo'],
    refs: [
        {ref: 'MainView', selector: 'main'} // Reference to main view
    ],

    init: function () {
        var me = this;
        //по умолчанию обновление карты разрешено
        Ext.updateMap = true;
        //обновление отдельных маршрутов по умолчанию запрещено
        Ext.updateRouteBuses = false;
        ;
        //обновление отдельных маршрутов по умолчанию запрещено
        //регистрация кнокпи на функцию
        me.control({
            'button[action=traffic]': {
                click: me.traffic
            }
        });
        me.control({
            'button[action=search]': {
                click: me.search
            }
        });

        me.control({
            'button[action=viewBuses]': {
                click: me.routes
            }
        });
    },

    traffic: function () {
        var map = Ext.getCmp("main").yMap;
        var actualProvider = new ymaps.traffic.provider.Actual({}, {infoLayerShown: true});
        if (Ext.traffic == false) {
            Ext.traffProvider.setMap(map);
            Ext.traffic = true;
        } else {
            Ext.traffProvider.setMap(null);
            Ext.traffic = false;
        }
    },

    /*Отображение автобусов отдельных маршрутов на карте*/
    routes: function (main) {

        var me = this;
        Ext.updateRouteBuses = false;
        //clearInterval(intervalID);
        updateRouteBuses(me);

        function updateRouteBuses(me) {
            Ext.updateRouteBuses = true;

            if (Ext.updateRouteBuses === true) {
                var userRoutes = new Array();
                var w = me.getMainView(),
                    userRoutes = w.down('#checkboxes').getChecked();
                if (userRoutes.length !== 0) {
                    var routes = new Array();
                    //получаем имена маршрутов
                    for (var i = 0; i <= userRoutes.length - 1; i++) {
                        routes.push(new Object({
                            route: userRoutes[i].boxLabel,
                            proj_ID: userRoutes[i].name
                        }));
                    }
                    routes = Ext.JSON.encode(routes);
                    //Ext.Ajax.timeout = 60000;
                    Ext.Ajax.request({
                        params: {
                            routes: routes
                        },
                        url: 'GetRouteBuses',
                        success: function (response) {
                            var ERROR = checkResponseServer(response);
                            if (ERROR) {
                                Ext.Msg.alert('Ошибка', ERROR);
                                return 0;
                            }
                            var routes = JSON.parse(response.responseText);
                            var map = Ext.getCmp("main");
                            map.markerGroup.clearLayers()
                            for (var i = 0; i <= routes.length - 1; i++) {
                                var bus = routes[i]
                                var lng = bus.last_lon_;
                                var lat = bus.last_lat_;
                                var lng2 = bus.lon2;
                                var lat2 = bus.lat2;
                                var lf = bus.lowfloor;
                                var dist = bus.dist;
                                if (true)
                                {
                                    //ordinary buses
                                    var busClass = '<div class="b-car b-car_blue b-car-direction-$[properties.direction]"></div>'
                                    if (lf === 1) {
                                        busClass = '<div class="b-car1 b-car_blue b-car-direction-$[properties.direction]"></div>'
                                    }
                                    var x = lat2 - lat
                                    var y = lng2 - lng

                                    var azimuth = Math.floor(Math.atan2(y, x) * 180 / Math.PI)

                                    L.marker([lat, lng], {
                                        icon: L.divIcon({
                                            className: 'b-car b-car_blue',
                                            iconUrl: '/CitizenCoddWebMaps/images/bus' + azimuth + '.png',
                                            iconSize: [32, 32],
                                        })
                                    }).addTo(map.markerGroup)
                                        .bindTooltip(bus.route_name_, { permanent: true, interactive: true });
                                }
                            }
                        },
                        failure: function () {
                            Ext.MessageBox.alert('Ошибка', 'Потеряно соединение с сервером');
                        }
                    });
                }
                if (userRoutes.length === 0) {
                    var map = Ext.getCmp("main");
                    map.markerGroup.clearLayers()
                }
            }
        }

        var intervalID = setInterval(function () {
            updateRouteBuses(me);
        }, 30000); //период обновления
    },

    /*Информация об автобусе*/
    search: function () {
        var w = this.getMainView(),
            busName = w.down('#searchBus').lastValue;
        Ext.Ajax.request({
            params: {
                busName: busName
            },
            url: 'GetInfoOfBus',
            success: function (response) {
                var ERROR = checkResponseServer(response);
                if (ERROR) {
                    Ext.Msg.alert('Ошибка', ERROR);
                    return 0;
                }
                var busesInfoWindow = Ext.widget('busesInfo', {info: response.responseText});
                busesInfoWindow.show();
            },
            failure: function () {
                Ext.MessageBox.alert('Ошибка', 'Потеряно соединение с сервером');
            }
        });
    },

});