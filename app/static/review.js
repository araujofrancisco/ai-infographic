(function () {

    var overlay = document.getElementById(
        "loading-overlay"
    );

    var overlayText = document.getElementById(
        "overlay-text"
    );

    function showOverlay(message) {

        if (!overlay) {
            return;
        }

        overlay.hidden = false;

        overlay.setAttribute(
            "aria-busy",
            "true"
        );

        if (overlayText) {
            overlayText.textContent =
                message || "Working…";
        }
    }

    function hideOverlay() {

        if (!overlay) {
            return;
        }

        overlay.hidden = true;

        overlay.setAttribute(
            "aria-busy",
            "false"
        );
    }

    function readContent() {

        var title = document.getElementById(
            "content-title"
        ).value;

        var subtitle = document.getElementById(
            "content-subtitle"
        ).value;

        var sections = [];

        document.querySelectorAll(
            ".section"
        ).forEach(function (node) {

            var bullets = node.querySelector(
                ".sec-bullets"
            ).value
                .split("\n")
                .map(function (item) {
                    return item.trim();
                })
                .filter(function (item) {
                    return item.length > 0;
                });

            sections.push({
                title: node.querySelector(
                    ".sec-title"
                ).value,
                short_description: node.querySelector(
                    ".sec-desc"
                ).value,
                bullet_points: bullets,
                visual_description: node.querySelector(
                    ".sec-visual"
                ).value
            });
        });

        return {
            title: title,
            subtitle: subtitle,
            sections: sections
        };
    }

    function saveContent() {

        var payload = {
            project_id: document.querySelector(
                "input[name='project_id']"
            ).value,
            content_json: JSON.stringify(
                readContent()
            )
        };

        var body = Object.keys(
            payload
        ).map(function (key) {
            return (
                encodeURIComponent(key)
                + "="
                + encodeURIComponent(
                    payload[key]
                )
            );
        }).join("&");

        return fetch(
            "/save-content?json=1",
            {
                method: "POST",
                headers: {
                    "Content-Type":
                        "application/x-www-form-urlencoded"
                },
                body: body
            }
        ).then(function (response) {

            return response.json().then(
                function (data) {

                    if (
                        !response.ok
                        || !data.ok
                    ) {

                        throw new Error(
                            data.error
                            || "Save failed"
                        );
                    }

                    return data;
                }
            );
        });
    }

    function showBanner(
        className,
        message
    ) {

        document.querySelectorAll(
            "." + className
        ).forEach(function (node) {
            node.remove();
        });

        var banner = document.createElement(
            "div"
        );

        banner.className = className;

        banner.textContent = message;

        var container = document.querySelector(
            ".container"
        );

        container.insertBefore(
            banner,
            container.querySelector(
                "form"
            )
        );
    }

    function showNotice(message) {

        showBanner(
            "notice",
            message
        );
    }

    function showError(message) {

        showBanner(
            "error error-inline",
            message
        );
    }

    var saveButton = document.getElementById(
        "save-button"
    );

    if (saveButton) {

        document.getElementById(
            "save-form"
        ).addEventListener(
            "submit",
            function (event) {

                event.preventDefault();

                var original = saveButton.textContent;

                saveButton.disabled = true;

                saveButton.textContent = "Saving…";

                showOverlay(
                    "Saving changes…"
                );

                saveContent()
                .then(function () {

                    hideOverlay();

                    saveButton.textContent = original;

                    saveButton.disabled = false;

                    showNotice(
                        "Saved ✓"
                    );
                })
                .catch(function (error) {

                    hideOverlay();

                    saveButton.textContent = original;

                    saveButton.disabled = false;

                    showError(
                        error.message
                    );
                });
            }
        );
    }

    var generateButton = document.getElementById(
        "generate-button"
    );

    if (generateButton) {

        generateButton.addEventListener(
            "click",
            function () {

                var original = (
                    generateButton.textContent
                );

                generateButton.disabled = true;

                generateButton.textContent =
                    "Saving and starting…";

                showOverlay(
                    "Saving changes and starting…"
                );

                saveContent()
                .then(function () {

                    var force = (
                        document.getElementById(
                            "force-regen"
                        ).checked
                    ) ? "1" : "0";

                    document.getElementById(
                        "force-input"
                    ).value = force;

                    document.getElementById(
                        "generate-form"
                    ).submit();
                })
                .catch(function (error) {

                    hideOverlay();

                    generateButton.disabled = false;

                    generateButton.textContent = original;

                    showError(
                        error.message
                    );
                });
            }
        );
    }

})();
