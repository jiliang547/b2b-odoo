{
    'name': 'Partner Hub Yonyou Connector',
    'version': '19.0.1.3.3',
    'author': 'Lucky Tone',
    'license': 'LGPL-3',
    'depends': ['b2b_management', 'b2b_erp_connector'],
    'data': ['security/ir.model.access.csv', 'security/order_rules.xml', 'data/config.xml',
             'data/progress_cron.xml', 'views/mapping.xml', 'views/orders.xml', 'views/progress.xml'],
    'assets': {'web.assets_frontend': [
        'b2b_yonyou/static/src/progress.js', 'b2b_yonyou/static/src/progress.scss',
    ]},
    'auto_install': ['b2b_management'],
    'installable': True,
    'application': False,
}
