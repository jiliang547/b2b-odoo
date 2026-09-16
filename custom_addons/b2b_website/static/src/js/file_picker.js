/** @odoo-module **/
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

class PaymentProofPicker extends Interaction {
    static selector = ".lt-file-picker";
    dynamicContent = {
        "input[type=file]": { "t-on-change": this.updateFilename },
    };
    start() { this.updateFilename(); }
    updateFilename() {
        const input = this.el.querySelector("input[type=file]");
        this.el.querySelector("[data-lt-file-name]").textContent =
            input.files?.[0]?.name || _t("No file selected");
    }
}
registry.category("public.interactions").add("b2b_website.payment_proof_picker", PaymentProofPicker);
