/*
 * Retyped admin dashboard helpers.
 *
 * Live refresh: an element with data-poll-url is re-fetched every few seconds
 * (request header X-Partial: 1) and its contents replaced. Polling continues
 * while the returned HTML contains a [data-keep-polling] marker.
 * Checked checkboxes inside the region are preserved across refreshes.
 *
 * Select all: a checkbox with data-select-all="name" toggles every checkbox
 * with that name.
 */
(function () {
  "use strict";

  var INTERVAL = 5000;

  function poll(region) {
    var url = region.getAttribute("data-poll-url");
    var timer = null;

    function schedule() {
      timer = window.setTimeout(tick, INTERVAL);
    }

    function tick() {
      if (document.hidden) {
        schedule();
        return;
      }
      var checked = Array.prototype.map.call(
        region.querySelectorAll("input[type=checkbox]:checked"),
        function (box) {
          return box.name + "=" + box.value;
        }
      );
      fetch(url, { headers: { "X-Partial": "1" }, credentials: "same-origin" })
        .then(function (response) {
          if (!response.ok) {
            throw new Error("HTTP " + response.status);
          }
          return response.text();
        })
        .then(function (html) {
          region.innerHTML = html;
          region.querySelectorAll("input[type=checkbox]").forEach(function (box) {
            if (checked.indexOf(box.name + "=" + box.value) !== -1) {
              box.checked = true;
            }
          });
          if (region.querySelector("[data-keep-polling]")) {
            schedule();
          }
        })
        .catch(function () {
          schedule(); // transient error: try again later
        });
    }

    if (region.querySelector("[data-keep-polling]")) {
      schedule();
    }
    return function () {
      window.clearTimeout(timer);
    };
  }

  document.addEventListener("change", function (event) {
    var target = event.target;
    var name = target.getAttribute && target.getAttribute("data-select-all");
    if (!name) {
      return;
    }
    document.querySelectorAll('input[type=checkbox][name="' + name + '"]').forEach(
      function (box) {
        box.checked = target.checked;
      }
    );
  });

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-poll-url]").forEach(poll);
  });
})();
