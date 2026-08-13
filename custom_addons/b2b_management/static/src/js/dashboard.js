/** @odoo-module **/

import {Component, onWillStart, useState} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

export class B2BManagementDashboard extends Component {
    static template = "b2b_management.Dashboard";

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.state = useState({loading: true, samples: 0, failedJobs: 0, approvedPartners: 0});
        onWillStart(async () => {
            const [samples, failedJobs, approvedPartners] = await Promise.all([
                this.orm.searchCount("b2b.sample.request", [["state", "in", ["submitted", "under_review"]]]),
                this.orm.searchCount("b2b.integration.job", [["state", "in", ["failed", "dead"]]]),
                this.orm.searchCount("res.partner", [["b2b_approved", "=", true], ["is_company", "=", true]]),
            ]);
            Object.assign(this.state, {loading: false, samples, failedJobs, approvedPartners});
        });
    }

    openAction(xmlId) {
        return this.action.doAction(xmlId);
    }
}

registry.category("actions").add("b2b_management.dashboard", B2BManagementDashboard);
