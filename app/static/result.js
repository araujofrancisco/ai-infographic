(function () {

    var tabs = Array.prototype.slice.call(
        document.querySelectorAll(
            ".viewer-tab"
        )
    );

    function activateTab(tab) {

        tabs.forEach(function (other) {

            var active = other === tab;

            other.classList.toggle(
                "active",
                active
            );

            other.setAttribute(
                "aria-selected",
                active ? "true" : "false"
            );

            var panel = document.getElementById(
                other.getAttribute(
                    "aria-controls"
                )
            );

            if (panel) {
                panel.hidden = !active;
            }
        });
    }

    tabs.forEach(function (tab) {

        tab.addEventListener(
            "click",
            function () {

                activateTab(tab);
            }
        );
    });

    var lightbox = document.getElementById(
        "lightbox"
    );

    var lightboxImg = document.getElementById(
        "lightbox-img"
    );

    var lightboxClose = document.getElementById(
        "lightbox-close"
    );

    var resultPng = document.getElementById(
        "result-png"
    );

    var lastFocus = null;

    function openLightbox() {

        if (!lightbox || !lightboxImg) {
            return;
        }

        lastFocus = document.activeElement;

        lightboxImg.src = resultPng.src;

        lightbox.hidden = false;

        if (lightboxClose) {
            lightboxClose.focus();
        }
    }

    function closeLightbox() {

        if (!lightbox) {
            return;
        }

        lightbox.hidden = true;

        if (
            lastFocus
            && lastFocus.focus
        ) {
            lastFocus.focus();
        }
    }

    if (
        resultPng
        && lightbox
    ) {

        resultPng.addEventListener(
            "click",
            openLightbox
        );

        if (lightboxClose) {

            lightboxClose.addEventListener(
                "click",
                closeLightbox
            );
        }

        lightbox.addEventListener(
            "click",
            function (event) {

                if (event.target === lightbox) {
                    closeLightbox();
                }
            }
        );

        document.addEventListener(
            "keydown",
            function (event) {

                if (
                    event.key === "Escape"
                    && !lightbox.hidden
                ) {
                    closeLightbox();
                }
            }
        );
    }

})();
