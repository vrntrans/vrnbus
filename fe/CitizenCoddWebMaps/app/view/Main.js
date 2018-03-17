// main view
Ext.define('CWM.view.Main', {
    alias: 'widget.main', // alias (xtype)
    extend: 'Ext.panel.Panel',
    title: 'МБУ ЦОДД "Веб карта"',
    id:'main',
   // map instance
            yMap: null,
            myPlacemark: null,
            // map cfg
            ymapConfig: {
                center: [51.6841, 39.2014],
                zoom: 12,
                cursor: 'help'
            },

            initComponent: function () {
                var me = this;
                me.routesBox = "";
                var box = new Array();

                Ext.Ajax.request({
                    url: 'GetBusesServlet',
                    async: false,
                    success: function(response){
                        var ERROR = checkResponseServer(response);
                        if (ERROR){
                            Ext.Msg.alert('Технические работы на сервере. Пожалуйста, попробуте зайти позже.', ERROR);
                            return 0;
                        }
                        var routes =  JSON.parse(response.responseText);  
                        //чекбоксы для выбора просмотра отдельных маршрутов 
                        for (var i=0; i<= routes.length-1; i++) {                  
                                box.push({
                                    name: routes[i].NAME_,
                                    id : routes[i].ID_
                                });
                        }
                    },
                    failure: function () {
                        Ext.MessageBox.alert('Ошибка', 'Потеряно соединение с сервером');
                    }
                    
                });
                me.routesBox = Ext.create('Ext.data.Store', {
                            fields: ['id', 'name'],
                            data : box
                        });
                                                                      
                var store = new Ext.data.Store({
                    fields: ['id', 'name'],
                    data: box
                });

                var comboBox = new Ext.form.ComboBox({
                    fieldLabel: 'My ComboBox',
                    typeAhead: true,
                    triggerAction: 'all',
                    mode: 'local',
                    store: store,
                    valueField: 'id',
                    displayField: 'name'
                });

                var items = [];

                comboBox.store.each(function (record) {
                    items.push({
                        boxLabel: record.get(comboBox.displayField),
                        name: record.get(comboBox.valueField)
                    });
                });

                var checkboxGroup = new Ext.form.CheckboxGroup({
                    xtype: 'checkboxgroup',
                    width: 300,
                    columns: 5,
                    items: items
                });
       
                me.tbar = [
                    {
                        text: 'Маршруты',
                        itemId: 'routes',                     
                        menu: [{
                                xtype: 'button',
                                text: ' Отобразить',
                                action: 'viewBuses'
                        },{
                                xtype: 'checkboxgroup',
                                itemId: 'checkboxes',
                                vertical: true,
                                items: checkboxGroup
                        }]
                    },
                    {
                        text: 'Поиск по автобусам',
                        itemId: 'searchBuses',
                        menu: [{
                                xtype: 'button',
                                text: ' Найти',
                                action: 'search'
                        },{
                                xtype: 'textfield',
                                itemId: 'searchBus',
                                allowBlank: false,
                                fieldLabel: 'Номер'
                        }]
                    },
                    {
                        itemId: 'traffic',
                        text: 'Пробки',
                        action: 'traffic'
                    }
                ];
                me.yMapId = "map-canvas";
                me.on('boxready', me.createYMap);
                me.on('boxready', me.getBuses);
                me.callParent(arguments);
            },
                
                /*Остановка с расписанием*/
                getBuses: function () {
                var me = this;
                var z = "";
                var data = "";
                var box2 = new Array();
                var nbuses;
                ymaps.ready(function () {
                    me.yMap.events.add('click', function (e) {
                    var coords = e.get('coords');                    
                    if (!me.yMap.balloon.isOpen()) {                
                        Ext.Ajax.request({params:{
                                        lat: coords[1].toPrecision(12),
                                        lon: coords[0].toPrecision(12)
                                    },
                            url: 'GetNextBus',
                            async: false,
                            success: function(response){
                                var ERROR = checkResponseServer(response);
                                if (ERROR){
                                    Ext.Msg.alert('Ошибка', ERROR);
                                    return 0;
                                }
                                nbuses =  JSON.parse(response.responseText);
                                if (nbuses[0] !== null){ 
                                for (var i = 0; i <= nbuses.length-1; i++) {
                                    if (nbuses[i].time_ == '0') nbuses[i].time_ = '-';
                                        box2.push({
                                            name: nbuses[i].rname_,
                                            time: nbuses[i].time_
                                        });
                                }}
                        },
                            failure: function () {
                                Ext.MessageBox.alert('Ошибка', 'Потеряно соединение с сервером');
                            }
                        });
                        if (nbuses[0] !== null){
                                        arr = [];
                                        for (var i = 0; i <= box2.length - 1; i++) {                  
                                        z = JSON.stringify(box2[i]);
                                        arr.push(z);                               
                                        } 

                                box2.forEach(function(item, i, box2){
                                        if (i !== 0) data += item.name + "&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp" + item.time+'\n';                                            
                                });
                                        me.yMap.balloon.open(coords, {
                                        contentHeader:box2[0].name,
                                        contentBody:
                                            '<p>Маршрут:    Время:'+ '<br/>'  
                                            + data.replace(/\n+/g, "<br/>") + '</p>',
                                        contentFooter:'<sup>*************</sup>'
                                        });
                                    }
                                    data = "";
                                    box2.splice(0);
                                    }
                                else {
                                    me.yMap.balloon.close();
                                }
                            });
                        });             
            },

            /*Создание веб карты*/
            createYMap: function () {
                var me = this;
                me.update('<div style="width: ' + me.getEl().getWidth() + 'px; height: ' + me.getEl().getHeight() + 'px;" id="' + me.yMapId + '"></div>');
                // me.update('<div id="mapid"></div>')
                    ymaps.ready(function () {
                        me.yMap = new ymaps.Map(document.getElementById(me.yMapId), me.ymapConfig, {projection: ymaps.projection.wgs84Mercator});
                        me.yMap.copyrights.add("Разработчик сервиса Меркулов Дмитрий. МБУ ЦОДД 'Веб карта'.");
                        me.yMap.behaviors.enable('scrollZoom');
                        //me.yMap.addCursor(ymaps.Cursor.GRAB);
                        me.yMap.controls
                        // Кнопка изменения масштаба.
                            .add('zoomControl', {left: 5, top: 5});
                    });
            }
        
});