(function () {

    var overlay = document.getElementById(
        "loading-overlay"
    );

    var overlayText = document.getElementById(
        "overlay-text"
    );

    var bannerRegion = document.getElementById(
        "banner-region"
    );

    var saveForm = document.getElementById(
        "save-form"
    );

    var sectionList = document.getElementById(
        "section-list"
    );

    var sectionTemplate = document.getElementById(
        "section-template"
    );

    var previewImg = document.getElementById(
        "preview-img"
    );

    var previewError = document.getElementById(
        "preview-error"
    );

    var MIN_SECTIONS = 3;

    var MAX_SECTIONS = 8;

    var NOTICE_DISMISS_MS = 5000;

    var PREVIEW_DEBOUNCE_MS = 500;

    var requestPreview = null;

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

        sectionList.querySelectorAll(
            ".section-block"
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

    function projectId() {

        var input = document.querySelector(
            "input[name='project_id']"
        );

        return input
            ? input.value
            : "";
    }

    function postForm(
        url,
        payload
    ) {

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
            url,
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

                        var error = new Error(
                            data.error
                            || "Request failed"
                        );

                        error.status = (
                            response.status
                        );

                        throw error;
                    }

                    return data;
                }
            );
        });
    }

    function saveContent() {

        return postForm(
            "/save-content?json=1",
            {
                project_id: projectId(),
                content_json: JSON.stringify(
                    readContent()
                )
            }
        );
    }

    function scheduleDismiss(node) {

        if (
            !node
            || !node.classList.contains(
                "notice"
            )
        ) {
            return;
        }

        window.setTimeout(
            function () {

                node.classList.add(
                    "dismissing"
                );

                window.setTimeout(
                    function () {

                        node.remove();
                    },
                    400
                );
            },
            NOTICE_DISMISS_MS
        );
    }

    function showBanner(
        className,
        message
    ) {

        if (!bannerRegion) {
            return;
        }

        bannerRegion
            .querySelectorAll(
                ".notice, .error"
            )
            .forEach(function (node) {
                node.remove();
            });

        var banner = document.createElement(
            "div"
        );

        banner.className = className;

        banner.textContent = message;

        bannerRegion.appendChild(
            banner
        );

        scheduleDismiss(
            banner
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

    function sections() {

        return sectionList.querySelectorAll(
            ".section-block"
        );
    }

    function updateSectionButtons() {

        var count = sections().length;

        var addButton = document.getElementById(
            "add-section"
        );

        if (addButton) {
            addButton.disabled = (
                count >= MAX_SECTIONS
            );
        }

        sectionList
            .querySelectorAll(
                ".section-remove"
            )
            .forEach(function (button) {

                button.disabled = (
                    count <= MIN_SECTIONS
                );
            });
    }

    function liveTitle(block) {

        var text = block.querySelector(
            ".section-title-text"
        );

        if (!text) {
            return;
        }

        text.textContent = (
            block.querySelector(
                ".sec-title"
            ).value.trim()
        ) || "Untitled section";
    }

    function renumber() {

        sections().forEach(
            function (block, index) {

                block.setAttribute(
                    "data-index",
                    String(
                        index
                    )
                );

                var number = block.querySelector(
                    ".section-number"
                );

                if (number) {
                    number.textContent =
                        "Section " + (index + 1);
                }

                liveTitle(
                    block
                );

                block.querySelectorAll(
                    ".sec-label"
                ).forEach(function (label) {

                    var kind = label.getAttribute(
                        "data-for"
                    );

                    var field = block.querySelector(
                        ".sec-" + kind
                    );

                    if (
                        field
                        && kind
                    ) {

                        var id = (
                            "sec-" + index + "-" + kind
                        );

                        field.id = id;

                        label.setAttribute(
                            "for",
                            id
                        );
                    }
                });
            }
        );
    }

    function addSection() {

        if (
            !sectionTemplate
            || sections().length >= MAX_SECTIONS
        ) {
            return;
        }

        var node = (
            sectionTemplate.content.firstElementChild
        ).cloneNode(true);

        sectionList.appendChild(
            node
        );

        renumber();

        updateSectionButtons();

        if (requestPreview) {
            requestPreview();
        }
    }

    function removeSection(block) {

        if (sections().length <= MIN_SECTIONS) {
            return;
        }

        block.remove();

        renumber();

        updateSectionButtons();

        if (requestPreview) {
            requestPreview();
        }
    }

    if (
        previewImg
        && projectId()
    ) {

        var previewSeq = 0;

        function requestPreviewInner() {

            var seq = ++previewSeq;

            var payload = {
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

            fetch(
                "/preview/" + encodeURIComponent(
                    projectId()
                ),
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/x-www-form-urlencoded"
                    },
                    body: body
                }
            ).then(function (response) {

                if (response.status === 400) {

                    return response.json().then(
                        function (data) {

                            if (seq !== previewSeq) {
                                return;
                            }

                            previewError.textContent =
                                data.error
                                || "Preview unavailable.";

                            previewError.hidden = false;
                        }
                    );
                }

                if (!response.ok) {

                    if (seq === previewSeq) {

                        previewError.textContent =
                            "Preview could not be rendered.";

                        previewError.hidden = false;
                    }

                    return;
                }

                return response.blob().then(
                    function (blob) {

                        if (seq !== previewSeq) {
                            return;
                        }

                        var url = URL.createObjectURL(
                            blob
                        );

                        if (
                            previewImg.dataset.blobUrl
                        ) {

                            URL.revokeObjectURL(
                                previewImg.dataset.blobUrl
                            );
                        }

                        previewImg.dataset.blobUrl = url;

                        previewImg.src = url;

                        previewError.hidden = true;
                    }
                );
            }).catch(function () {

                // Transient failure: keep the last preview.
            });
        }

        var previewTimer = null;

        saveForm.addEventListener(
            "input",
            function () {

                window.clearTimeout(
                    previewTimer
                );

                previewTimer = window.setTimeout(
                    requestPreviewInner,
                    PREVIEW_DEBOUNCE_MS
                );
            }
        );

        requestPreviewInner();

        requestPreview = requestPreviewInner;
    }

    document.querySelectorAll(
        "#banner-region .notice"
    ).forEach(
        scheduleDismiss
    );

    if (sectionList) {

        updateSectionButtons();

        renumber();

        sectionList.addEventListener(
            "click",
            function (event) {

                var remove = event.target.closest(
                    ".section-remove"
                );

                if (
                    remove
                    && !remove.disabled
                ) {

                    removeSection(
                        remove.closest(
                            ".section-block"
                        )
                    );
                }
            }
        );

        sectionList.addEventListener(
            "input",
            function (event) {

                if (
                    event.target.classList.contains(
                        "sec-title"
                    )
                ) {

                    liveTitle(
                        event.target.closest(
                            ".section-block"
                        )
                    );
                }
            }
        );

        var addButton = document.getElementById(
            "add-section"
        );

        if (addButton) {

            addButton.addEventListener(
                "click",
                addSection
            );
        }

        var expandAll = document.getElementById(
            "expand-all"
        );

        if (expandAll) {

            expandAll.addEventListener(
                "click",
                function () {

                    sections().forEach(
                        function (block) {
                            block.open = true;
                        }
                    );
                }
            );
        }

        var collapseAll = document.getElementById(
            "collapse-all"
        );

        if (collapseAll) {

            collapseAll.addEventListener(
                "click",
                function () {

                    sections().forEach(
                        function (block) {
                            block.open = false;
                        }
                    );
                }
            );
        }
    }

    var saveButton = document.getElementById(
        "save-button"
    );

    if (
        saveButton
        && saveForm
    ) {

        saveForm.addEventListener(
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
