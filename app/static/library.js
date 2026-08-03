(function () {

    var errorBox = document.getElementById(
        "delete-error"
    );

    var errorText = document.getElementById(
        "delete-error-text"
    );

    function showError(message) {

        if (!errorBox || !errorText) {

            alert(message);

            return;
        }

        errorText.textContent = message;

        errorBox.hidden = false;

        errorBox.scrollIntoView({
            behavior: "smooth",
            block: "nearest"
        });
    }

    function hideError() {

        if (errorBox) {

            errorBox.hidden = true;
        }
    }

    document.querySelectorAll(
        "[data-delete]"
    ).forEach(function (button) {

        button.addEventListener(
            "click",
            function () {

                var projectId = button.getAttribute(
                    "data-delete"
                );

                var topic = button.getAttribute(
                    "data-topic"
                ) || "this infographic";

                var message = (
                    "Delete \"" + topic + "\"?\n" +
                    "This permanently removes the project " +
                    "and its rendered files."
                );

                if (!window.confirm(message)) {

                    return;
                }

                fetch(
                    "/projects/" + projectId + "/delete",
                    {
                        method: "POST"
                    }
                )
                .then(function (response) {

                    return response.json().then(
                        function (data) {

                            if (!response.ok || !data.ok) {

                                throw new Error(
                                    data.error
                                    || "Delete failed"
                                );
                            }

                            return data;
                        }
                    );
                })
                .then(function () {

                    hideError();

                    window.location.reload();
                })
                .catch(function (error) {

                    showError(
                        error.message
                    );
                });
            }
        );
    });

})();
