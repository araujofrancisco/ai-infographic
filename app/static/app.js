(function () {

    var overlay = document.getElementById(
        "loading-overlay"
    );

    function showOverlay() {

        if (overlay) {
            overlay.hidden = false;
        }
    }

    function hideOverlay() {

        if (overlay) {
            overlay.hidden = true;
        }
    }

    window.addEventListener(
        "pageshow",
        hideOverlay
    );

    document.querySelectorAll(
        "form[data-loading]"
    ).forEach(function (form) {

        form.addEventListener(
            "submit",
            function () {

                showOverlay();

                var button = form.querySelector(
                    "button[type='submit']"
                );

                if (button) {
                    button.disabled = true;
                    button.textContent = "Working…";
                }
            }
        );
    });

})();
