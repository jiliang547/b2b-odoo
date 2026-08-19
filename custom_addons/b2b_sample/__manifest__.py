{
    "name": "Lucky Tone B2B Sample Requests",
    "summary": "Partner Hub sample requests, review, Portal isolation, and ERP handoff",
    "version": "19.0.1.1.0",
    "category": "Sales/B2B",
    "license": "LGPL-3",
    "author": "Lucky Tone",
    "depends": ["b2b_core", "b2b_erp_connector", "portal", "mail"],
    "data": [
        "security/b2b_sample_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/sample_request_views.xml",
    ],
    "installable": True,
    "application": False,
    "post_init_hook": "post_init_hook",
}
