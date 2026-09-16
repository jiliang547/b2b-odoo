{
    'name': 'Partner Hub Multi-company Sales',
    'version': '19.0.1.3.8',
    'license': 'LGPL-3',
    'author': 'Lucky Tone',
    'depends': ['b2b_website', 'stock_dropshipping', 'sale_purchase_stock_inter_company_rules'],
    'data': ['data/sequences.xml', 'security/pricing.xml', 'security/ir.model.access.csv', 'views/configuration.xml', 'views/setup.xml', 'views/backend.xml'],
    'installable': True,
    'auto_install': ['b2b_website'],
    'application': False,
}
