/**
 * clientside.js — Client-side callbacks for Spin Rate.
 * Handles click-to-pin interactions and opacity dimming.
 */

window.dash_clientside = Object.assign({}, window.dash_clientside, {
    spinrate: {
        /**
         * Click-to-pin: capture clickData and toggle selected-sku store.
         * Clicking the same bubble again dismisses (sets to null).
         *
         * @param {Object} clickData - Plotly click event data
         * @param {string|null} currentSku - Currently selected SKU ID
         * @returns {string|null} Updated selected SKU ID
         */
        handle_click: function(clickData, currentSku) {
            if (!clickData || !clickData.points || clickData.points.length === 0) {
                return window.dash_clientside.no_update;
            }

            var point = clickData.points[0];
            var customdata = point.customdata;

            // customdata[0] is the SKU ID.
            if (!customdata || !customdata[0]) {
                return window.dash_clientside.no_update;
            }

            var clickedSku = customdata[0];

            // Toggle: click same SKU again to dismiss.
            if (currentSku === clickedSku) {
                return null;
            }

            return clickedSku;
        }
    }
});
