"""Dash brand frame helper — header, footer, content wrapper."""

from dash import html


def wrap(layout, tool_name: str, footer_note: str = None, no_container: bool = False):
    footer_children = [
        html.P(
            [
                "Built by ",
                html.A(
                    "Lailara LLC",
                    href="https://lailarallc.com",
                    target="_blank",
                    rel="noopener",
                ),
            ]
        ),
    ]
    if footer_note:
        footer_children.append(html.P(footer_note, className="lailara-footer-note"))

    if no_container:
        main_content = html.Main(layout, className="lailara-main")
    else:
        main_content = html.Main(
            html.Div(layout, className="lailara-container"),
            className="lailara-main",
        )

    return html.Div(
        [
            html.Header(
                html.Nav(
                    [
                        html.A(
                            "Lailara LLC",
                            href="https://lailarallc.com",
                            className="lailara-wordmark",
                            target="_blank",
                            rel="noopener",
                        ),
                        html.Span(tool_name, className="lailara-tool-name"),
                    ],
                    className="lailara-nav-inner",
                ),
                className="lailara-header",
            ),
            main_content,
            html.Footer(
                html.Div(footer_children, className="lailara-footer-inner"),
                className="lailara-footer",
            ),
        ],
        className="lailara-page",
    )
