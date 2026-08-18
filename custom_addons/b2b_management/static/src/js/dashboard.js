/** @odoo-module **/

import {Component, onWillStart, useState} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {useService} from "@web/core/utils/hooks";

export class B2BManagementDashboard extends Component {
    static template = "b2b_management.Dashboard";

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            pendingApprovals: 0,
            samples: 0,
            openService: 0,
            failedJobs: 0,
        });
        onWillStart(async () => {
            const safeCount = async (model, domain) => {
                try {
                    return await this.orm.searchCount(model, domain);
                } catch {
                    return 0;
                }
            };
            const [pendingApprovals, samples, openService, failedJobs] = await Promise.all([
                safeCount("res.partner", [["b2b_approved", "=", false], ["is_company", "=", true], ["customer_rank", ">", 0]]),
                safeCount("b2b.sample.request", [["state", "in", ["submitted", "under_review"]]]),
                safeCount("helpdesk.ticket", [["stage_id.fold", "=", false]]),
                safeCount("b2b.integration.job", [["state", "in", ["failed", "dead"]]]),
            ]);
            Object.assign(this.state, {
                loading: false,
                pendingApprovals,
                samples,
                openService,
                failedJobs,
            });
        });
    }

    openAction(xmlId) {
        return this.action.doAction(xmlId);
    }
}

registry.category("actions").add("b2b_management.dashboard", B2BManagementDashboard);
