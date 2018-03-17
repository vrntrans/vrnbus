Ext.define('CWM.controller.Main', {
    extend: 'Ext.app.Controller',
    views: ['CWM.view.Main', 'CWM.view.BusesInfo'],
    refs: [
        {ref: 'MainView', selector: 'main'} // Reference to main view
    ],

    init: function() {  
        var me = this;
        //по умолчанию обновление карты разрешено
        Ext.updateMap = true;
        //обновление отдельных маршрутов по умолчанию запрещено
        Ext.updateRouteBuses = false;;
        //обновление отдельных маршрутов по умолчанию запрещено
        //регистрация кнокпи на функцию
        me.control({'button[action=traffic]':{
                            click: me.traffic
                }
        });
        me.control({'button[action=search]': {
                click: me.search
            }
        });
        
        me.control({'button[action=viewBuses]': {
                click: me.routes
            }
        });
    },

    traffic:function(){
        var map = Ext.getCmp("main").yMap;
        var actualProvider = new ymaps.traffic.provider.Actual({}, {infoLayerShown: true});
        if (Ext.traffic == false){        
            Ext.traffProvider.setMap(map);
            Ext.traffic = true;
        }else{
            Ext.traffProvider.setMap(null);
            Ext.traffic = false;
        }
    },
   
    /*Отображение автобусов отдельных маршрутов на карте*/
     routes: function(main){

        var me = this;
        Ext.updateRouteBuses = false;
        //clearInterval(intervalID);
        updateRouteBuses(me);
        function updateRouteBuses(me){
            Ext.updateRouteBuses = true;
            
            if (Ext.updateRouteBuses === true){
                var userRoutes = new Array();
                    var w = me.getMainView(),
                    userRoutes = w.down('#checkboxes').getChecked();                    
                    if (userRoutes.length !== 0){
                    var routes = new Array();
                    //получаем имена маршрутов
                    for (var i = 0 ; i <= userRoutes.length-1; i++){                        
                        routes.push(new Object({
                                route: userRoutes[i].boxLabel,
                                proj_ID: userRoutes[i].name
                        }));
                    } 
                    routes = Ext.JSON.encode(routes);
                    //Ext.Ajax.timeout = 60000;
                    Ext.Ajax.request({
                            params:{
                                routes: routes
                            },
                            url: 'GetRouteBuses',
                            success: function(response){
                                var ERROR = checkResponseServer(response);
                                if (ERROR){
                                    Ext.Msg.alert('Ошибка', ERROR);
                                    return 0;
                                }
                                var routes =  JSON.parse(response.responseText);
                                var map = Ext.getCmp("main");
                                if (map.yMap.geoObjects.removeAll) {
                                    map.yMap.geoObjects.removeAll()
                                }
                                else {
                                    map.yMap.geoObjects.each(function (geoObject) {
                                        map.yMap.geoObjects.remove(geoObject);
                                    });
                                }
                                var spee = [];
                                for (var i = 0; i <= routes.length-1; i++){
                                    var bus = routes[i]
                                    spee.push(bus.route_name_);
                                    var lng = bus.last_lon_;
                                    var lat = bus.last_lat_;
                                    var lng2 = bus.lon2;
                                    var lat2 = bus.lat2;
                                    var lf = bus.lowfloor;
                                    var dist = bus.dist;
                                    if (lng !== 0 && lat !== 0 && lng2 !== 0 && lat2 !== 0 && lng !== lng2 && lat!== lat2&& dist < 1){
                                        //ordinary buses
                                        var busClass = '<div class="b-car b-car_blue b-car-direction-$[properties.direction]"></div>'
                                        if (lf === 1){
                                            busClass = '<div class="b-car1 b-car_blue b-car-direction-$[properties.direction]"></div>'
                                        }
                                        var car = new Car({iconLayout: ymaps.templateLayoutFactory.createClass(busClass)});
                                        var sp = spee.pop();
                                        map.yMap.geoObjects.add(car);
                                        car.properties.set('hintContent', sp);
                                        car.geometry.setCoordinates([lat2, lng2]);
                                        car.properties.set('direction', bus.azimuth/10);
                                    }
                            //if some coords are nulls or the same
                            else{
                                    var azmth = parseInt(bus.azimuth/10);
                                    if (bus.lowfloor === 1)
                                        azmth = "0" + azmth;
                                    if (lng ===0 || lat === 0)
                                    {
                                        lng = lng2;
                                        lat = lat2;
                                    }
                                        var Placemark = new ymaps.Placemark([lat, lng], {
                                            
                                            hintContent : spee.pop()
                                            //iconContentOffset : [50] 
                                         }, {                                             
                                            iconImageHref: '/CitizenCoddWebMaps/images/bus'+azmth+'.png',
                                             iconImageSize: [40, 40],
                                             iconImageOffset: [-20, -20],
                                             iconContentOffset : [3, 35]
                                         });
                                         
                                map.yMap.geoObjects.add(Placemark);
                            }
                                

                              }  //map.yMap.geoObjects.add(Ext.myGeoObject);
                            },
                            failure: function(){
                                Ext.MessageBox.alert('Ошибка', 'Потеряно соединение с сервером');
                            }
                        });
                    }
                        if (userRoutes.length === 0){
                        var map = Ext.getCmp("main");
                        map.yMap.geoObjects.each(function(geoObject){
                        map.yMap.geoObjects.remove(geoObject);
                        });
                    }
            }}
            var intervalID =setInterval(function(){updateRouteBuses(me);}, 30000); //период обновления
    },
            
    /*Информация об автобусе*/
    search: function(){
        var w = this.getMainView(),
        busName = w.down('#searchBus').lastValue;
        Ext.Ajax.request({
            params:{
                busName: busName
            },
            url:'GetInfoOfBus',
            success: function(response){
                var ERROR = checkResponseServer(response);
                if (ERROR){
                    Ext.Msg.alert('Ошибка', ERROR);
                    return 0;
                }
                var busesInfoWindow = Ext.widget('busesInfo', {info: response.responseText});
                busesInfoWindow.show();
            },
            failure: function(){
                Ext.MessageBox.alert('Ошибка', 'Потеряно соединение с сервером');
            }
        });
    },
    
});