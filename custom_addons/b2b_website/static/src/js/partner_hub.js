/** @odoo-module **/

import {rpc} from "@web/core/network/rpc";

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

function initializeCartForms() {
    document.querySelectorAll("[data-lt-cart-form]").forEach((form) => {
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const button = form.querySelector("button[type='submit']");
            const status = form.querySelector("[data-lt-cart-status]");
            const quantity = Number(form.elements.add_qty.value);
            if (!Number.isFinite(quantity) || quantity <= 0 || quantity > 10000) {
                status.textContent = "Enter a valid quantity.";
                return;
            }
            button.disabled = true;
            status.textContent = "Adding product…";
            try {
                await rpc("/shop/cart/add", {
                    product_template_id: Number(form.elements.product_template_id.value),
                    product_id: Number(form.elements.product_id.value),
                    uom_id: Number(form.elements.uom_id.value),
                    quantity,
                });
                window.location.assign("/shop/cart");
            } catch (_error) {
                button.disabled = false;
                status.textContent = "We could not add this product. Please try again.";
            }
        });
    });
}

function initializePartnerHub() {
    initializeNavigation();
    initializeFilters();
    initializeGalleries();
    initializeCartForms();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializePartnerHub, {once: true});
} else {
    initializePartnerHub();
}
