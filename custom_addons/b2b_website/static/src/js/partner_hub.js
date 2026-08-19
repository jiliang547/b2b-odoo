/** @odoo-module **/

import {rpc} from "@web/core/network/rpc";

function synchronizeCartQuantity(quantity) {
    const cartQuantity = Math.max(0, Number(quantity) || 0);
    try {
        window.sessionStorage.setItem("website_sale_cart_quantity", String(cartQuantity));
    } catch (_error) {
        // The server-rendered quantity remains the fallback when storage is unavailable.
    }
    document.querySelectorAll(".my_cart_quantity").forEach((element) => {
        element.textContent = String(cartQuantity);
        element.classList.toggle("d-none", cartQuantity === 0);
        if (cartQuantity) {
            element.dataset.orderId = element.dataset.orderId || "";
        } else {
            delete element.dataset.orderId;
        }
    });
}

async function initializeCartQuantity() {
    try {
        synchronizeCartQuantity(await rpc("/shop/cart/quantity"));
    } catch (_error) {
        // Keep the server-rendered Odoo quantity if the refresh request fails.
    }
}

function initializeNavigation() {
    document.querySelectorAll(".lt-nav-toggle").forEach((button) => {
        button.addEventListener("click", () => {
            const navigation = document.getElementById(button.getAttribute("aria-controls"));
            const expanded = button.getAttribute("aria-expanded") === "true";
            button.setAttribute("aria-expanded", String(!expanded));
            navigation?.classList.toggle("is-open", !expanded);
        });
    });
}

function initializeFilters() {
    document.querySelectorAll("[data-lt-filter-toggle]").forEach((button) => {
        button.addEventListener("click", () => {
            const panel = document.querySelector(".lt-filter-panel");
            panel?.classList.toggle("is-open");
        });
    });
}

function initializeCatalogView() {
    document.querySelectorAll("[data-lt-auto-submit]").forEach((select) => {
        select.addEventListener("change", () => select.form?.requestSubmit());
    });
    document.querySelectorAll("[data-lt-view]").forEach((button) => {
        button.addEventListener("click", () => {
            const grid = document.querySelector("[data-lt-product-grid]");
            const mode = button.dataset.ltView;
            grid?.classList.toggle("is-list", mode === "list");
            button.parentElement?.querySelectorAll("button").forEach(
                (item) => item.classList.toggle("is-active", item === button)
            );
            try {
                window.localStorage.setItem("lt-product-view", mode);
            } catch (_error) {
                // Storage may be blocked; the view toggle still works for this page.
            }
        });
    });
    let preferred = "grid";
    try {
        preferred = window.localStorage.getItem("lt-product-view") || "grid";
    } catch (_error) {
        // Keep the accessible grid default.
    }
    document.querySelector(`[data-lt-view="${preferred}"]`)?.click();
}

function initializeGalleries() {
    document.querySelectorAll("[data-lt-gallery]").forEach((gallery) => {
        const image = gallery.querySelector("[data-lt-gallery-image]");
        const videoPanes = gallery.querySelectorAll(".lt-gallery__video");
        gallery.querySelectorAll(".lt-gallery__thumbs button").forEach((button) => {
            button.addEventListener("click", () => {
                gallery.querySelectorAll(".lt-gallery__thumbs button").forEach(
                    (item) => item.classList.remove("is-active")
                );
                button.classList.add("is-active");
                videoPanes.forEach((pane) => pane.classList.add("d-none"));
                const target = button.dataset.videoTarget;
                if (target) {
                    image?.classList.add("d-none");
                    document.getElementById(target)?.classList.remove("d-none");
                } else if (image) {
                    image.src = button.dataset.imageSrc;
                    image.classList.remove("d-none");
                }
            });
        });
    });
}

function formatQuantity(quantity) {
    return Number(quantity).toLocaleString(document.documentElement.lang || "en", {
        maximumFractionDigits: 3,
    });
}

function initializeDetailTabs() {
    document.querySelectorAll("[data-lt-detail-tabs]").forEach((tabs) => {
        const buttons = [...tabs.querySelectorAll("[data-lt-detail-tab]")];
        const panels = [...tabs.querySelectorAll("[data-lt-detail-panel]")];
        const activate = (button, focus = false) => {
            const name = button.dataset.ltDetailTab;
            buttons.forEach((item) => {
                const selected = item === button;
                item.classList.toggle("is-active", selected);
                item.setAttribute("aria-selected", String(selected));
                item.tabIndex = selected ? 0 : -1;
            });
            panels.forEach((panel) => {
                const selected = panel.dataset.ltDetailPanel === name;
                panel.classList.toggle("is-active", selected);
                panel.hidden = !selected;
            });
            if (focus) {
                button.focus();
            }
        };
        buttons.forEach((button, index) => {
            button.addEventListener("click", () => activate(button));
            button.addEventListener("keydown", (event) => {
                if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
                    return;
                }
                event.preventDefault();
                let targetIndex = index;
                if (event.key === "ArrowLeft") targetIndex = (index - 1 + buttons.length) % buttons.length;
                if (event.key === "ArrowRight") targetIndex = (index + 1) % buttons.length;
                if (event.key === "Home") targetIndex = 0;
                if (event.key === "End") targetIndex = buttons.length - 1;
                activate(buttons[targetIndex], true);
            });
        });
        if (buttons.length) {
            activate(buttons.find((button) => button.classList.contains("is-active")) || buttons[0]);
        }
    });
}

function initializeQuantityControls() {
    document.querySelectorAll("[data-lt-quantity-control]").forEach((control) => {
        const input = control.querySelector("input[type='number']");
        const change = (direction) => {
            const minimum = Number(input.min || 1);
            const maximum = Number(input.max || 10000);
            const step = Number(input.step || 1);
            const next = Math.min(maximum, Math.max(minimum, Number(input.value || minimum) + direction * step));
            input.value = String(next);
            input.dispatchEvent(new Event("change", {bubbles: true}));
        };
        control.querySelector("[data-lt-quantity-decrease]")?.addEventListener("click", () => change(-1));
        control.querySelector("[data-lt-quantity-increase]")?.addEventListener("click", () => change(1));
        input?.addEventListener("blur", () => {
            const minimum = Number(input.min || 1);
            const maximum = Number(input.max || 10000);
            input.value = String(Math.min(maximum, Math.max(minimum, Number(input.value || minimum))));
        });
    });
}

function initializeCartForms() {
    document.querySelectorAll("[data-lt-cart-form]").forEach((form) => {
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const button = form.querySelector("button[type='submit']");
            const status = form.querySelector("[data-lt-cart-status]");
            const quantity = Number(form.elements.add_qty.value);
            const minimum = Number(form.elements.add_qty.min || 0);
            const maximum = Number(form.elements.add_qty.max || 10000);
            if (!Number.isFinite(quantity) || quantity < minimum || quantity > maximum) {
                status.textContent = `Enter a quantity between ${formatQuantity(minimum)} and ${formatQuantity(maximum)}.`;
                return;
            }
            button.disabled = true;
            status.textContent = "Adding product…";
            try {
                const result = await rpc("/shop/cart/add", {
                    product_template_id: Number(form.elements.product_template_id.value),
                    product_id: Number(form.elements.product_id.value),
                    uom_id: Number(form.elements.uom_id.value),
                    quantity,
                });
                synchronizeCartQuantity(result.cart_quantity);
                status.textContent = "Added to cart.";
                button.disabled = false;
            } catch (_error) {
                button.disabled = false;
                status.textContent = "We could not add this product. Please try again.";
            }
        });
    });
}

function initializeVariantPickers() {
    document.querySelectorAll("[data-lt-variant-picker]").forEach((picker) => {
        const panel = picker.closest(".lt-purchase-panel");
        const form = panel?.querySelector("[data-lt-cart-form]");
        const quantityInput = form?.elements.add_qty;
        let requestNumber = 0;

        const refreshCombination = async () => {
            const currentRequest = ++requestNumber;
            const combination = [...picker.querySelectorAll("[data-lt-variant-attribute]")]
                .map((select) => Number(select.value))
                .filter(Number.isFinite);
            const quantity = Math.max(1, Number(quantityInput?.value || 1));
            const status = picker.querySelector("[data-lt-variant-status]");
            status.textContent = "Checking availability…";
            try {
                const info = await rpc("/website_sale/get_combination_info", {
                    product_template_id: Number(picker.dataset.templateId),
                    product_id: Number(picker.dataset.productId),
                    combination,
                    add_qty: quantity,
                    uom_id: Number(form?.elements.uom_id?.value || 0) || null,
                });
                if (currentRequest !== requestNumber) {
                    return;
                }
                const available = Boolean(info.is_combination_possible && info.product_id);
                status.textContent = available ? "Selected configuration is available." : "This configuration is not available.";
                picker.dataset.productId = String(info.product_id || 0);
                if (form) {
                    form.elements.product_id.value = info.product_id || 0;
                    if (info.b2b_uom_id) {
                        form.elements.uom_id.value = info.b2b_uom_id;
                    }
                    form.querySelector("button[type='submit']").disabled = !available;
                }
                const minimum = Math.max(1, Number(info.b2b_minimum_quantity || 1));
                const step = Math.max(Number(info.b2b_quantity_step || 1), 0.001);
                if (quantityInput) {
                    quantityInput.min = String(minimum);
                    quantityInput.step = String(step);
                }
                panel.querySelectorAll("[data-lt-minimum-quantity], [data-lt-minimum-hint]").forEach((element) => {
                    element.textContent = formatQuantity(minimum);
                });
                panel.querySelectorAll("[data-lt-procurement-uom], [data-lt-minimum-uom], [data-lt-price-uom]").forEach((element) => {
                    element.textContent = info.b2b_uom_name || "unit";
                });
                const stockBadge = panel.querySelector("[data-lt-stock-badge]");
                if (stockBadge) {
                    [...stockBadge.classList].filter((name) => name.startsWith("lt-stock-badge--")).forEach((name) => stockBadge.classList.remove(name));
                    stockBadge.classList.add(`lt-stock-badge--${info.b2b_stock_state || "available"}`);
                }
                const stockLabel = panel.querySelector("[data-lt-stock-label]");
                if (stockLabel) stockLabel.textContent = info.b2b_stock_label || "Available";
                const stockQuantity = panel.querySelector("[data-lt-stock-quantity]");
                if (stockQuantity) {
                    stockQuantity.classList.toggle("d-none", !info.b2b_show_stock_quantity);
                    stockQuantity.textContent = ` (${formatQuantity(info.b2b_stock_quantity || 0)} ${info.b2b_uom_name || "unit"})`;
                }
                const leadTime = panel.querySelector("[data-lt-lead-time]");
                if (leadTime) {
                    leadTime.textContent = info.b2b_lead_time_days == null
                        ? "Contact sales"
                        : info.b2b_lead_time_days > 0
                            ? `${formatQuantity(info.b2b_lead_time_days)} days`
                            : "Ready to ship";
                }
                panel.querySelectorAll("[data-lt-variant-sku]").forEach((element) => {
                    element.textContent = info.b2b_sku || "Model on request";
                });
                const image = document.querySelector("[data-lt-gallery-image]");
                if (image && info.product_id) {
                    image.src = `/web/image/product.product/${info.product_id}/image_1024`;
                }
                const priceElement = panel.querySelector("[data-lt-price-value]");
                if (priceElement && info.b2b_can_view_price && Number.isFinite(Number(info.price))) {
                    try {
                        priceElement.textContent = new Intl.NumberFormat(document.documentElement.lang || "en", {
                            style: "currency",
                            currency: info.b2b_currency_code,
                        }).format(Number(info.price));
                    } catch (_error) {
                        priceElement.textContent = `${info.b2b_currency_code} ${Number(info.price).toFixed(2)}`;
                    }
                }
                if (quantityInput && Number(quantityInput.value) < minimum) {
                    quantityInput.value = String(minimum);
                    quantityInput.dispatchEvent(new Event("change", {bubbles: true}));
                }
                const sampleLink = panel.querySelector("[data-lt-sample-link]");
                if (sampleLink && info.b2b_sample_url) {
                    sampleLink.href = sampleLink.href.includes("/web/login")
                        ? `/web/login?redirect=${encodeURIComponent(info.b2b_sample_url)}`
                        : info.b2b_sample_url;
                }
            } catch (_error) {
                if (currentRequest === requestNumber) {
                    status.textContent = "We could not validate this configuration. Please try again.";
                    form?.querySelector("button[type='submit']")?.setAttribute("disabled", "disabled");
                }
            }
        };

        picker.querySelectorAll("[data-lt-variant-attribute]").forEach((select) => {
            select.addEventListener("change", refreshCombination);
        });
        quantityInput?.addEventListener("change", refreshCombination);
    });
}

function initializePartnerHub() {
    initializeNavigation();
    initializeFilters();
    initializeCatalogView();
    initializeGalleries();
    initializeDetailTabs();
    initializeQuantityControls();
    initializeVariantPickers();
    initializeCartForms();
    initializeCartQuantity();
    initializeAccountMenus();
    initializeSubmissionForms();
    initializePaymentStatus();
}

function resetSubmissionForm(form) {
    form.dataset.ltSubmitting = "false";
    form.removeAttribute("aria-busy");
    form.querySelectorAll("button[type='submit'], input[type='submit']").forEach((button) => {
        button.disabled = false;
        if (button.dataset.ltOriginalLabel) {
            if (button instanceof HTMLInputElement) {
                button.value = button.dataset.ltOriginalLabel;
            } else {
                button.innerHTML = button.dataset.ltOriginalLabel;
            }
        }
    });
    const status = form.querySelector("[data-lt-submit-status]");
    if (status) {
        status.textContent = "";
    }
}

function initializeSubmissionForms() {
    const forms = [...document.querySelectorAll("form[data-lt-submit-once]")];
    forms.forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (form.dataset.ltSubmitting === "true") {
                event.preventDefault();
                return;
            }
            form.dataset.ltSubmitting = "true";
            form.setAttribute("aria-busy", "true");
            form.querySelectorAll("button[type='submit'], input[type='submit']").forEach((button) => {
                button.dataset.ltOriginalLabel ||= button instanceof HTMLInputElement
                    ? button.value
                    : button.innerHTML;
                button.disabled = true;
                const label = button.dataset.ltSubmittingLabel || "Submitting…";
                if (button instanceof HTMLInputElement) {
                    button.value = label;
                } else {
                    button.innerHTML = `<i class="fa fa-circle-notch fa-spin" aria-hidden="true"></i> ${label}`;
                }
            });
            const status = form.querySelector("[data-lt-submit-status]");
            if (status) {
                status.textContent = "Please wait. Your request is being submitted.";
            }
        });
    });
    window.addEventListener("pageshow", () => {
        forms.forEach(resetSubmissionForm);
    });
}

function initializePaymentStatus() {
    const statusPage = document.querySelector("[data-lt-payment-status]");
    if (!statusPage) {
        return;
    }
    const startedAt = Date.now();
    const provider = statusPage.dataset.providerCode;
    const thresholdSeconds = provider === "demo" ? 8 : 45;
    const elapsed = statusPage.querySelector("[data-lt-payment-elapsed]");
    const liveStatus = statusPage.querySelector("[data-lt-payment-live]");
    const processing = statusPage.querySelector("[data-lt-payment-processing]");
    const pending = statusPage.querySelector("[data-lt-payment-pending]");

    const updateConnectivity = () => {
        if (liveStatus) {
            liveStatus.textContent = navigator.onLine
                ? "Automatic payment checks are continuing."
                : "Connection lost. We will continue checking when you are back online.";
        }
    };
    updateConnectivity();
    window.addEventListener("online", updateConnectivity);
    window.addEventListener("offline", updateConnectivity);

    const timer = window.setInterval(() => {
        const seconds = Math.floor((Date.now() - startedAt) / 1000);
        if (elapsed) {
            elapsed.textContent = `${seconds}s`;
        }
        if (seconds >= thresholdSeconds) {
            window.clearInterval(timer);
            processing?.setAttribute("hidden", "hidden");
            pending?.removeAttribute("hidden");
            statusPage.classList.add("is-pending");
        }
    }, 1000);

    statusPage.querySelector("[data-lt-payment-recheck]")?.addEventListener("click", () => {
        window.location.reload();
    });
}

function initializeAccountMenus() {
    const menus = [...document.querySelectorAll("details.lt-account-menu")];
    if (!menus.length) {
        return;
    }
    document.addEventListener("pointerdown", (event) => {
        menus.forEach((menu) => {
            if (menu.open && !menu.contains(event.target)) {
                menu.open = false;
            }
        });
    });
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") {
            return;
        }
        menus.forEach((menu) => {
            if (menu.open) {
                menu.open = false;
                menu.querySelector("summary")?.focus();
            }
        });
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializePartnerHub, {once: true});
} else {
    initializePartnerHub();
}
