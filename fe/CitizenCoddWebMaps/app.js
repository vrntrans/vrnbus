Ext.application({
    requires: ['Ext.container.Viewport'],
    name: 'CWM',

    appFolder: 'app',
    
    controllers: ['CWM.controller.Main'],

    launch: function() {
        Ext.create('Ext.container.Viewport', {
            layout: 'fit',
            items: [
                {
                    xtype: 'main'
                }
            ]
        });
    }
});