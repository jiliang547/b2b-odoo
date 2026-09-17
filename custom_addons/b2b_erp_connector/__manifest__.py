{
    "name": "Lucky Tone B2B ERP Connector",
    "summary": "Reliable Partner Hub ERP adapters and asynchronous jobs",
    "version": "19.0.1.1.0",
    "category": "Sales/B2B",
    "license": "LGPL-3",
    "author": "Lucky Tone",
    "depends": ["b2b_core", "sale_management", "mail"],
    "data": [
        "security/b2b_erp_security.xml",
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/integration_job_views.xml",
        "views/res_config_settings_views.xml",
        "views/sale_order_views.xml",
    ],
    "installable": True,
    "application": False,
}
