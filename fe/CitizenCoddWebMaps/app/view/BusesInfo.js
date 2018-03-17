Ext.define('CWM.view.BusesInfo', {
    alias: 'widget.busesInfo', // alias (xtype)
    extend: 'Ext.window.Window',
    title: 'Возможные ТС',
    width: "50%",
    height: 400,
    id: 'busesInfo',
    config: {info:''},
    
    constructor: function() {
        this.callParent(arguments);
    },
            
    initComponent: function () {
        this.callParent(arguments);
        var info = JSON.parse(this.getInfo());
        
        //заполняем массив автобусов(1..n) с инфой 
        var buses = new Array();
        for (var i = 0; i <= info.length-1; i++){
            buses.push(new Object({
                    number: i+1,
                    name: info[i].name_,
                    projName: info[i].projName,
                    routeName: info[i].route_name_,
                    lastTime: datef("dd.MM.YYYY hh:mm", info[i].last_time_)
                }));
            }
                //создание хранидища данных для отображения
         Ext.create('Ext.data.Store', {
            storeId: 'infoOfBuses',
            fields: ['number', 'name', 'projName', 'routeName', 'lastTime'],
            data: {'items': buses},
            proxy: {
                 type: 'memory',
                 reader: {
                    type: 'json',
                    root: 'items'
                 }
            }
         });
                
         //проверка на существование
         var cmp = Ext.getCmp('busesInfo');
         if(cmp !== undefined)
            cmp.destroy();
                
         //окно с информацией
        var count = buses.length-1;
         var panel = Ext.create('Ext.grid.Panel', {
            title: 'Полученные автобусы ' + count,
            id: 'busesInfoPanel',
            store: Ext.data.StoreManager.lookup('infoOfBuses'),
            autoScroll : true,
            columns: [
                { text: '№',  dataIndex: 'number', width: '5%'},
                { text: 'Номер',  dataIndex: 'name', width: '15%'},
                { text: 'Перевозчик', dataIndex: 'projName', width: '30%'},
                { text: 'Маршрут', dataIndex: 'routeName', width: '20%'},
                { text: 'Последний отклик', dataIndex: 'lastTime', width: '30%'}
            ],
            height: 400,
            width: 'auto'
         });
         this.add(panel);
         this.doLayout();
    }
});
