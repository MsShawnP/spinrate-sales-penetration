/**
 * clientside.js — Client-side callbacks for Spin Rate.
 * Handles click-to-pin interactions and opacity dimming.
 */

/**
 * Fix Plotly legend text clipping caused by the Source Sans 3 web-font
 * loading race. `font-display: swap` (lailara-frame.css) paints legend
 * text with a fallback font immediately, then swaps to Source Sans 3
 * once it downloads. Plotly measures legend entry widths ONCE, at
 * layout time, using whichever font is active at that instant -- if the
 * chart draws before the swap completes, entries are positioned using
 * the (narrower) fallback font's metrics, and the wider Source Sans 3
 * glyphs that paint in afterward overflow past the boundary Plotly
 * already committed to. Plotly never re-measures on its own, and no
 * amount of container CSS can reach inside its <svg> coordinate layout.
 *
 * Fix: once the browser confirms the font has actually finished
 * loading, force every currently-drawn plot to resize/relayout so
 * Plotly re-measures legend text with the correct, final metrics. If
 * the chart hasn't drawn yet at that point, it draws AFTER the font is
 * ready and never hits the race in the first place -- this only needs
 * to run once.
 */
(function () {
    function resizePlotlyCharts() {
        document.querySelectorAll(".js-plotly-plot").forEach(function (gd) {
            if (window.Plotly && gd._fullLayout) {
                window.Plotly.Plots.resize(gd);
            }
        });
    }

    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(resizePlotlyCharts);
    }
})();

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
