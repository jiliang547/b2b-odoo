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

function isQuantityAligned(quantity, minimum, step) {
    if (!Number.isFinite(quantity) || !Number.isFinite(minimum) || !Number.isFinite(step) || step <= 0) {
        return false;
    }
    const increments = (quantity - minimum) / step;
    return Math.abs(increments - Math.round(increments)) <= Math.max(1e-9, step * 1e-9);
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
            const step = Number(form.elements.add_qty.step || 1);
            if (!isQuantityAligned(quantity, minimum, step)) {
                status.textContent = `Start at ${formatQuantity(minimum)} and order in steps of ${formatQuantity(step)}.`;
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
                const resourceList = document.querySelector("[data-lt-resource-list]");
                const resourceEmpty = document.querySelector("[data-lt-resource-empty]");
                if (resourceList && Array.isArray(info.b2b_resources)) {
                    resourceList.replaceChildren(...info.b2b_resources.map((resource) => {
                        const article = document.createElement("article");
                        article.className = "lt-resource-card";
                        const icon = document.createElement("div");
                        icon.className = "lt-resource-card__icon";
                        icon.textContent = resource.format || "FILE";
                        const copy = document.createElement("div");
                        const heading = document.createElement("h3");
                        heading.textContent = resource.name;
                        const meta = document.createElement("p");
                        meta.textContent = [resource.version && `v${resource.version}`, resource.language, resource.format, resource.size_mb && `${resource.size_mb} MB`].filter(Boolean).join(" · ");
                        copy.append(heading, meta);
                        const link = document.createElement("a");
                        link.className = "lt-btn lt-btn--outline lt-btn--small";
                        link.href = resource.url;
                        link.textContent = "Download";
                        article.append(icon, copy, link);
                        return article;
                    }));
                    resourceEmpty?.toggleAttribute("hidden", info.b2b_resources.length > 0);
                }
            } catch (_error) {
                if (currentRequest === requestNumber) {
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

function initializeServiceProductFilter() {
    const order = document.getElementById("service-order");
    const product = document.querySelector("[data-lt-service-product]");
    if (!order || !product) return;
    const options = [...product.querySelectorAll("option[data-order-id]")];
    const refresh = () => {
        const orderId = order.value;
        let first = null;
        options.forEach((option) => {
            const visible = Boolean(orderId && option.dataset.orderId === orderId);
            option.hidden = !visible;
            option.disabled = !visible;
            if (visible && !first) first = option;
        });
        if (!options.some((option) => !option.hidden && option.value === product.value)) {
            product.value = "";
        }
        product.options[0].textContent = orderId
            ? (first ? "Select an ordered product" : "No eligible products on this order")
            : "Select an order first";
    };
    order.addEventListener("change", refresh);
    refresh();
}

function initializeCategoryBrowsers() {
    document.querySelectorAll("[data-pg-category-browser]").forEach((browser) => {
        const grid = browser.querySelector("[data-pg-category-grid]");
        const trail = browser.querySelector("[data-pg-category-trail]");
        const breadcrumbs = browser.querySelector("[data-pg-category-breadcrumbs]");
        const back = browser.querySelector("[data-pg-category-back]");
        const brandId = Number(browser.dataset.brandId || 0);
        const stack = [false];

        const productUrl = (categoryId) => {
            const params = new URLSearchParams({category: String(categoryId)});
            if (brandId) params.set("brand", String(brandId));
            return `/products?${params.toString()}`;
        };
        const load = async (parentId, push = true) => {
            browser.classList.add("is-loading");
            const previousHeight = browser.getBoundingClientRect().height;
            browser.style.height = `${previousHeight}px`;
            try {
                const data = await rpc("/b2b/categories", {
                    parent_id: parentId || false,
                    brand_id: brandId || false,
                });
                if (push && stack.at(-1) !== parentId) stack.push(parentId);
                grid.replaceChildren();
                data.categories.forEach((category) => {
                    const button = document.createElement("button");
                    button.type = "button";
                    button.dataset.categoryId = String(category.id);
                    button.dataset.hasChildren = category.has_children ? "1" : "0";
                    const visual = document.createElement("span");
                    const image = document.createElement("img");
                    image.src = category.image_url;
                    image.alt = category.name;
                    image.loading = "lazy";
                    visual.append(image);
                    const name = document.createElement("strong");
                    name.textContent = category.name;
                    button.append(visual, name);
                    grid.append(button);
                });
                breadcrumbs.replaceChildren();
                const all = document.createElement("button");
                all.type = "button";
                all.textContent = brandId ? "Brand" : "All";
                all.addEventListener("click", () => load(false, false));
                breadcrumbs.append(all);
                data.breadcrumbs.forEach((category, index) => {
                    const separator = document.createElement("span");
                    separator.textContent = "/";
                    breadcrumbs.append(separator);
                    if (index === data.breadcrumbs.length - 1) {
                        const current = document.createElement("b");
                        current.textContent = category.name;
                        breadcrumbs.append(current);
                    } else {
                        const item = document.createElement("button");
                        item.type = "button";
                        item.textContent = category.name;
                        item.addEventListener("click", () => load(category.id, false));
                        breadcrumbs.append(item);
                    }
                });
                trail.hidden = !parentId;
            } catch (_error) {
                const message = document.createElement("p");
                message.className = "lt-alert lt-alert--error";
                message.textContent = "Categories could not be loaded. Please try again.";
                grid.replaceChildren(message);
            } finally {
                // Measure the natural content height without letting the browser paint
                // the intermediate auto-sized state. Using scrollHeight while the old
                // fixed height is active prevents transitions to a shorter category list.
                browser.style.height = "auto";
                const nextHeight = browser.getBoundingClientRect().height;
                browser.style.height = `${previousHeight}px`;
                browser.getBoundingClientRect();
                browser.classList.add("is-animating");
                browser.classList.remove("is-loading");
                requestAnimationFrame(() => {
                    browser.style.height = `${nextHeight}px`;
                });
                window.setTimeout(() => {
                    browser.classList.remove("is-animating");
                    browser.style.height = "auto";
                }, 380);
            }
        };
        grid?.addEventListener("click", (event) => {
            const button = event.target.closest("button[data-category-id]");
            if (!button) return;
            const id = Number(button.dataset.categoryId);
            if (button.dataset.hasChildren === "1") load(id);
            else window.location.assign(productUrl(id));
        });
        back?.addEventListener("click", () => {
            if (stack.length > 1) stack.pop();
            load(stack.at(-1) || false, false);
        });
    });
}

function initializeHorizontalCarousels() {
    document.querySelectorAll("[data-pg-carousel]").forEach((carousel) => {
        const track = carousel.querySelector("[data-pg-carousel-track]");
        carousel.querySelectorAll("[data-pg-carousel-scroll]").forEach((button) => {
            button.addEventListener("click", () => {
                track?.scrollBy({
                    left: (button.dataset.pgCarouselScroll === "left" ? -1 : 1)
                        * Math.max(280, track.clientWidth * 0.75),
                    behavior: "smooth",
                });
            });
        });
    });
}

function initializeFeaturedProducts() {
    document.querySelectorAll("[data-pg-featured]").forEach((featured) => {
        const tabs = [...featured.querySelectorAll("[data-pg-featured-tab]")];
        const panels = [...featured.querySelectorAll("[data-pg-featured-panel]")];
        tabs.forEach((tab) => tab.addEventListener("click", () => {
            tabs.forEach((item) => {
                const selected = item === tab;
                item.classList.toggle("is-active", selected);
                item.setAttribute("aria-selected", String(selected));
            });
            panels.forEach((panel) => {
                const selected = panel.dataset.pgFeaturedPanel === tab.dataset.pgFeaturedTab;
                panel.classList.toggle("is-active", selected);
                panel.hidden = !selected;
            });
        }));
        featured.querySelectorAll("[data-pg-scroll]").forEach((button) => {
            button.addEventListener("click", () => {
                const track = button.parentElement.querySelector("[data-pg-featured-track]");
                track?.scrollBy({
                    left: (button.dataset.pgScroll === "left" ? -1 : 1) * Math.max(280, track.clientWidth * 0.8),
                    behavior: "smooth",
                });
            });
        });
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
    initializeServiceProductFilter();
    initializeCategoryBrowsers();
    initializeFeaturedProducts();
    initializeHorizontalCarousels();
    initializeCartForms();
    initializeCartQuantity();
    initializeAccountMenus();
    initializePortalSidebar();
    initializeFaq();
    initializeSubmissionForms();
    initializePaymentStatus();
    initializeCompanyOnboarding();
}

function initializeFaq() {
    const root = document.querySelector("[data-pg-faq]");
    const search = document.querySelector("[data-pg-faq-search]");
    if (!root || !search) {
        return;
    }
    const buttons = [...root.querySelectorAll("[data-pg-faq-category]")];
    const items = [...root.querySelectorAll("[data-pg-faq-item]")];
    const empty = root.querySelector("[data-pg-faq-empty]");
    let category = "all";
    const apply = () => {
        const query = search.value.trim().toLocaleLowerCase();
        let visible = 0;
        items.forEach((item) => {
            const categoryMatch = category === "all" || item.dataset.pgFaqItem === category;
            const textMatch = !query || (item.dataset.pgFaqText || "").includes(query);
            item.hidden = !(categoryMatch && textMatch);
            visible += item.hidden ? 0 : 1;
        });
        if (empty) {
            empty.hidden = visible !== 0;
        }
    };
    buttons.forEach((button) => button.addEventListener("click", () => {
        category = button.dataset.pgFaqCategory || "all";
        buttons.forEach((item) => item.classList.toggle("is-active", item === button));
        apply();
    }));
    search.addEventListener("input", apply);
}

function initializePortalSidebar() {
    const shell = document.querySelector(".lt-portal-shell");
    const toggle = shell?.querySelector("[data-lt-sidebar-toggle]");
    if (!shell || !toggle) {
        return;
    }
    const sync = () => {
        const expanded = !shell.classList.contains("is-sidebar-collapsed");
        toggle.setAttribute("aria-expanded", String(expanded));
        toggle.setAttribute("aria-label", expanded ? "Collapse account navigation" : "Expand account navigation");
    };
    toggle.addEventListener("click", () => {
        shell.classList.toggle("is-sidebar-collapsed");
        sync();
    });
    sync();
}

function resetSubmissionForm(form) {
    form.dataset.ltSubmitting = "false";
    form.removeAttribute("aria-busy");
    form.querySelectorAll("button[type='submit'], input[type='submit']").forEach((button) => {
        button.disabled = false;
        button.style.removeProperty("width");
        button.style.removeProperty("height");
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
                const buttonRect = button.getBoundingClientRect();
                button.style.width = `${buttonRect.width}px`;
                button.style.height = `${buttonRect.height}px`;
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
    const menus = [...document.querySelectorAll("details.lt-account-menu, details.lt-locale-menu")];
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

function initializeCompanyOnboarding() {
    const dialog = document.querySelector("[data-lt-company-onboarding]");
    if (!dialog) {
        return;
    }
    const storageKey = `lt-company-onboarding-${dialog.dataset.ltCompanyOnboarding}`;
    try {
        if (window.sessionStorage.getItem(storageKey)) {
            return;
        }
        window.sessionStorage.setItem(storageKey, "shown");
    } catch (_error) {
        // The reminder can still be displayed when browser storage is blocked.
    }
    const close = () => {
        dialog.hidden = true;
        document.body.classList.remove("lt-has-company-onboarding-dialog");
    };
    dialog.querySelectorAll("[data-lt-company-onboarding-close]").forEach(
        (button) => button.addEventListener("click", close)
    );
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !dialog.hidden) {
            close();
        }
    });
    dialog.hidden = false;
    document.body.classList.add("lt-has-company-onboarding-dialog");
    dialog.querySelector("a, button:not(.lt-company-onboarding-dialog__backdrop)")?.focus();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializePartnerHub, {once: true});
} else {
    initializePartnerHub();
}
