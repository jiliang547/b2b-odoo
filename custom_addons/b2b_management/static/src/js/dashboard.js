/** @odoo-module **/

import {Component, onWillStart, useState} from "@odoo/owl";
import {registry} from "@web/core/registry";
import {user} from "@web/core/user";
import {useService} from "@web/core/utils/hooks";

export class B2BManagementDashboard extends Component {
    static template = "b2b_management.Dashboard";

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.state = useState({
            loading: true,
            newContactRequests: 0,
            pendingRegistrations: 0,
            pendingApplications: 0,
            samples: 0,
            openService: 0,
            failedJobs: 0,
            canUseSales: false,
            canUseService: false,
            canViewErp: false,
            canUseRepairs: false,
        });
        onWillStart(async () => {
            const safeCount = async (model, domain) => {
                try {
                    return await this.orm.searchCount(model, domain);
                } catch {
                    return 0;
                }
            };
            const [canUseSales, canUseService, canViewErp, canUseRepairs] = await Promise.all([
                user.hasGroup("sales_team.group_sale_salesman"),
                user.hasGroup("helpdesk.group_helpdesk_user"),
                user.hasGroup("b2b_core.group_b2b_operator"),
                user.hasGroup("stock.group_stock_user"),
            ]);
            const [newContactRequests, pendingRegistrations, pendingApplications, samples, openService, failedJobs] = await Promise.all([
                safeCount("b2b.contact.request", [["state", "=", "new"]]),
                safeCount("b2b.registration.application", [["state", "=", "pending"]]),
                safeCount("b2b.contact.request", [["request_type", "=", "partnership"], ["state", "in", ["new", "in_progress"]]]),
                safeCount("b2b.sample.request", [["state", "in", ["submitted", "under_review"]]]),
                safeCount("helpdesk.ticket", [["stage_id.fold", "=", false]]),
                safeCount("b2b.integration.job", [["state", "in", ["failed", "dead"]]]),
            ]);
            Object.assign(this.state, {
                loading: false,
                newContactRequests,
                pendingRegistrations,
                pendingApplications,
                samples,
                openService,
                failedJobs,
                canUseSales,
                canUseService,
                canViewErp,
                canUseRepairs,
            });
        });
    }

    openAction(xmlId) {
        return this.action.doAction(xmlId);
    }
}

registry.category("actions").add("b2b_management.dashboard", B2BManagementDashboard);
