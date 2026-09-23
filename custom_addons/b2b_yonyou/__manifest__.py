{
    'name': 'Partner Hub Yonyou Connector',
    'version': '19.0.1.2.0',
    'author': 'Lucky Tone',
    'license': 'LGPL-3',
    'depends': ['b2b_management', 'b2b_erp_connector'],
    'data': ['security/ir.model.access.csv', 'security/order_rules.xml', 'data/config.xml', 'views/mapping.xml', 'views/orders.xml'],
    'auto_install': ['b2b_management'],
    'installable': True,
    'application': False,
}
