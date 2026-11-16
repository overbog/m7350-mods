// SPDX-License-Identifier: GPL-2.0-only
(function () {
    var deadline = 0;
    try {
        deadline = Number(window.sessionStorage.getItem("m7350-mode-switch")) || 0;
        window.sessionStorage.removeItem("m7350-mode-switch");
    } catch (error) {}
    var duringSwitch = Date.now() < deadline;
    if (duringSwitch) {
        // OEM can redirect before the settings page detects the USB move.
        var note = document.getElementById("noteDiv");
        var password = document.getElementById("password");
        if (note && password && /[?&](kickedOut|timeout)(?:&|$)/.test(location.search)) {
            note.hidden = true;
            password.addEventListener("input", function () { note.hidden = false; }, {once: true});
        }
        var message = document.getElementById("m7350-login-switch");
        message.textContent = "Sign in again to continue after switching modes.";
        message.classList.remove("hide");
    }

    function refresh() {
        var request = new XMLHttpRequest();
        request.open("GET", "cgi-bin/m7350l2?switch-state");
        request.timeout = 4000;
        request.onloadend = function () {
            var state;
            if (request.status === 200) {
                try { state = JSON.parse(request.responseText); } catch (error) {}
            }
            if (state && ["OEM", "VPN", "Unavailable"].indexOf(state.mode) >= 0) {
                document.getElementById("m7350-login-mode-value").textContent =
                    state.switching ? "Switching…" : state.mode;
                document.getElementById("m7350-login-mode").classList.remove("hide");
                if (!state.switching) return;
            }
            if (duringSwitch && Date.now() < deadline) {
                window.setTimeout(refresh, 1500);
            }
        };
        request.send();
    }
    refresh();
})();
