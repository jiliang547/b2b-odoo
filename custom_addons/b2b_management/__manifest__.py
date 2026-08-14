{
    "name": "Lucky Tone B2B Management",
    "summary": "Installable management application for the Lucky Tone Partner Hub",
    "version": "19.0.1.0.0",
    "category": "Sales/B2B",
    "license": "LGPL-3",
    "author": "Lucky Tone",
    "depends": ["b2b_website", "sale_management"],
    "data": ["views/b2b_management_menus.xml"],
    "assets": {
        "web.assets_backend": [
            "b2b_management/static/src/js/dashboard.js",
            "b2b_management/static/src/xml/dashboard.xml",
            "b2b_management/static/src/scss/dashboard.scss",
        ],
    },
    "installable": True,
    "application": True,
}
